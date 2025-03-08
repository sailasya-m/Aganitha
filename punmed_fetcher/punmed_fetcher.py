"""
PubMed Paper Fetcher - A script to fetch and filter research papers from PubMed
based on author affiliations with pharmaceutical or biotech companies.
"""

import csv
import io
import re
import sys
import time
import argparse
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple, Union, TextIO
import xml.etree.ElementTree as ET

import requests


@dataclass
class Author:
    """Represents an author of a research paper."""
    name: str
    affiliation: Optional[str] = None
    email: Optional[str] = None
    is_corresponding: bool = False
    is_non_academic: bool = False
    company: Optional[str] = None


@dataclass
class Paper:
    """Represents a research paper with its metadata."""
    pubmed_id: str
    title: str
    publication_date: str
    authors: List[Author]

    @property
    def non_academic_authors(self) -> List[Author]:
        """Return a list of authors affiliated with non-academic institutions."""
        return [author for author in self.authors if author.is_non_academic]

    @property
    def company_affiliations(self) -> Set[str]:
        """Return a set of unique company affiliations."""
        companies = set()
        for author in self.non_academic_authors:
            if author.company:
                companies.add(author.company)
        return companies

    @property
    def corresponding_author_email(self) -> Optional[str]:
        """Return the email of the corresponding author if available."""
        for author in self.authors:
            if author.is_corresponding and author.email:
                return author.email
        return None


class PubMedFetcher:
    """Class to fetch and process papers from PubMed."""
    
    # Base URLs for PubMed API
    ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    
    # Academic keywords to identify non-academic affiliations (inverse matching)
    ACADEMIC_KEYWORDS = [
        "university", "college", "institute", "school", "academia", 
        "hospital", "clinic", "medical center", "center for", "laboratory of", 
        "national", "federal", "ministry", "department of health"
    ]
    
    # Company identifiers
    COMPANY_IDENTIFIERS = [
        "inc", "llc", "ltd", "corp", "corporation", "pharmaceuticals", 
        "pharma", "biotech", "biosciences", "therapeutics", "biopharmaceuticals",
        "laboratories", "labs", "gmbh", "sa", "ag", "bv", "co."
    ]
    
    # Regex pattern for email extraction
    EMAIL_PATTERN = r'[\w\.-]+@[\w\.-]+\.\w+'
    
    def __init__(self, debug: bool = False):
        """Initialize the PubMed fetcher.
        
        Args:
            debug: Whether to print debug information during execution.
        """
        self.debug = debug
    
    def _debug_print(self, message: str) -> None:
        """Print debug messages if debug mode is enabled.
        
        Args:
            message: The debug message to print.
        """
        if self.debug:
            print(f"[DEBUG] {message}", file=sys.stderr)
    
    def search_papers(self, query: str, max_results: int = 100) -> List[str]:
        """Search PubMed for papers matching the query.
        
        Args:
            query: The search query in PubMed syntax.
            max_results: Maximum number of results to fetch.
            
        Returns:
            A list of PubMed IDs matching the query.
        """
        self._debug_print(f"Searching PubMed with query: {query}")
        
        params = {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": max_results,
            "usehistory": "y"
        }
        
        try:
            response = requests.get(self.ESEARCH_URL, params=params)
            response.raise_for_status()
            
            data = response.json()
            id_list = data.get("esearchresult", {}).get("idlist", [])
            
            self._debug_print(f"Found {len(id_list)} papers")
            return id_list
            
        except requests.exceptions.RequestException as e:
            self._debug_print(f"Error searching PubMed: {e}")
            return []
    
    def fetch_paper_details(self, pubmed_ids: List[str]) -> List[Paper]:
        """Fetch detailed information for a list of PubMed IDs.
        
        Args:
            pubmed_ids: A list of PubMed IDs to fetch details for.
            
        Returns:
            A list of Paper objects containing the paper details.
        """
        if not pubmed_ids:
            return []
            
        self._debug_print(f"Fetching details for {len(pubmed_ids)} papers")
        
        # Process in batches to avoid overwhelming the API
        batch_size = 20
        all_papers = []
        
        for i in range(0, len(pubmed_ids), batch_size):
            batch_ids = pubmed_ids[i:i + batch_size]
            
            params = {
                "db": "pubmed",
                "id": ",".join(batch_ids),
                "retmode": "xml"
            }
            
            try:
                response = requests.get(self.EFETCH_URL, params=params)
                response.raise_for_status()
                
                papers = self._parse_xml_response(response.text)
                all_papers.extend(papers)
                
                self._debug_print(f"Processed batch {i//batch_size + 1}/{(len(pubmed_ids)-1)//batch_size + 1}")
                
                # Respect API rate limits
                time.sleep(0.33)  # At most 3 requests per second
                
            except requests.exceptions.RequestException as e:
                self._debug_print(f"Error fetching paper details: {e}")
                continue
                
        return all_papers
    
    def _parse_xml_response(self, xml_text: str) -> List[Paper]:
        """Parse the XML response from PubMed.
        
        Args:
            xml_text: The XML response from PubMed.
            
        Returns:
            A list of Paper objects containing the paper details.
        """
        papers = []
        try:
            root = ET.fromstring(xml_text)
            
            for article_element in root.findall(".//PubmedArticle"):
                paper = self._extract_paper_data(article_element)
                if paper:
                    papers.append(paper)
                    
        except ET.ParseError as e:
            self._debug_print(f"Error parsing XML: {e}")
            
        return papers
    
    def _extract_paper_data(self, article_element: ET.Element) -> Optional[Paper]:
        """Extract paper data from an XML element.
        
        Args:
            article_element: An XML element representing a paper.
            
        Returns:
            A Paper object containing the paper details, or None if extraction failed.
        """
        try:
            # Extract PubMed ID
            pmid_element = article_element.find(".//PMID")
            if pmid_element is None or not pmid_element.text:
                return None
                
            pubmed_id = pmid_element.text
            
            # Extract title
            title_element = article_element.find(".//ArticleTitle")
            title = title_element.text if title_element is not None and title_element.text else "Unknown Title"
            
            # Extract publication date
            pub_date = "Unknown Date"
            pub_date_elements = article_element.findall(".//PubDate/*")
            if pub_date_elements:
                pub_date_parts = []
                for element in pub_date_elements:
                    if element.tag in ["Year", "Month", "Day"] and element.text:
                        pub_date_parts.append(element.text)
                if pub_date_parts:
                    pub_date = "-".join(pub_date_parts)
            
            # Extract authors and their affiliations
            authors = []
            author_elements = article_element.findall(".//Author")
            
            for author_element in author_elements:
                last_name = author_element.find("LastName")
                fore_name = author_element.find("ForeName")
                
                last_name_text = last_name.text if last_name is not None and last_name.text else ""
                fore_name_text = fore_name.text if fore_name is not None and fore_name.text else ""
                
                name = f"{last_name_text}, {fore_name_text}".strip(", ")
                if not name:
                    continue
                
                # Extract affiliation
                affiliation_element = author_element.find(".//Affiliation")
                affiliation = affiliation_element.text if affiliation_element is not None and affiliation_element.text else None
                
                # Check if the author has a corresponding author tag or identifier
                is_corresponding = False
                if author_element.get("ValidYN") == "Y" and author_element.get("EqualContrib") == "Y":
                    is_corresponding = True
                
                # Extract email if available
                email = None
                if affiliation:
                    email_match = re.search(self.EMAIL_PATTERN, affiliation)
                    if email_match:
                        email = email_match.group(0)
                
                # Check if author is from a non-academic institution
                is_non_academic, company = self._check_non_academic_affiliation(affiliation)
                
                author = Author(
                    name=name,
                    affiliation=affiliation,
                    email=email,
                    is_corresponding=is_corresponding,
                    is_non_academic=is_non_academic,
                    company=company
                )
                
                authors.append(author)
            
            # Try to identify corresponding author if not already identified
            if not any(author.is_corresponding for author in authors) and authors:
                # Look for any author with an email
                for author in authors:
                    if author.email:
                        author.is_corresponding = True
                        break
                
                # If still no corresponding author, just pick the first one
                if not any(author.is_corresponding for author in authors):
                    authors[0].is_corresponding = True
            
            return Paper(
                pubmed_id=pubmed_id,
                title=title,
                publication_date=pub_date,
                authors=authors
            )
            
        except Exception as e:
            self._debug_print(f"Error extracting paper data: {e}")
            return None
    
    def _check_non_academic_affiliation(self, affiliation: Optional[str]) -> Tuple[bool, Optional[str]]:
        """Check if an affiliation is non-academic and extract company name.
        
        Args:
            affiliation: The affiliation text to check.
            
        Returns:
            A tuple containing:
                - A boolean indicating if the affiliation is non-academic.
                - The extracted company name, or None if not found.
        """
        if not affiliation:
            return False, None
        
        affiliation_lower = affiliation.lower()
        
        # Check if the affiliation has academic keywords
        has_academic_keywords = any(keyword.lower() in affiliation_lower for keyword in self.ACADEMIC_KEYWORDS)
        
        # If it has academic keywords, it's probably academic
        if has_academic_keywords:
            return False, None
        
        # Check for company identifiers
        for identifier in self.COMPANY_IDENTIFIERS:
            pattern = rf'\b\w+\s+{re.escape(identifier)}\b|\b\w+{re.escape(identifier)}\b'
            match = re.search(pattern, affiliation_lower)
            if match:
                # Extract the full company name
                company_name = self._extract_company_name(affiliation, match.group(0))
                return True, company_name
        
        # Additional biotech/pharma specific keywords
        biotech_keywords = ["bioscience", "pharmaceuticals", "pharma", "biotech", "therapeutics", "biopharma"]
        for keyword in biotech_keywords:
            if keyword in affiliation_lower:
                company_name = self._extract_company_name(affiliation, keyword)
                return True, company_name
        
        # If no specific company identifier was found, check for basic signs
        if "," in affiliation and not has_academic_keywords:
            # Might be a company, extract the first part before a comma
            company_name = affiliation.split(",")[0].strip()
            return True, company_name
        
        return False, None
    
    def _extract_company_name(self, affiliation: str, matched_text: str) -> str:
        """Extract the full company name from an affiliation string.
        
        Args:
            affiliation: The full affiliation text.
            matched_text: The matched company identifier.
            
        Returns:
            The extracted company name.
        """
        # Simple company name extraction - get the sentence or segment containing the match
        index = affiliation.lower().find(matched_text.lower())
        if index == -1:
            return matched_text
        
        # Get the segment containing the match
        start = max(0, affiliation.rfind(",", 0, index))
        if start == 0:
            start = 0
        else:
            start += 1  # Skip the comma
            
        end = affiliation.find(",", index)
        if end == -1:
            end = len(affiliation)
            
        segment = affiliation[start:end].strip()
        
        # Clean up the segment
        segment = re.sub(r'\s+', ' ', segment)
        segment = segment.strip(".,;:()-")
        
        return segment

    def filter_papers_with_pharma_authors(self, papers: List[Paper]) -> List[Paper]:
        """Filter papers to include only those with pharmaceutical/biotech authors.
        
        Args:
            papers: A list of Paper objects to filter.
            
        Returns:
            A filtered list of Paper objects.
        """
        filtered_papers = []
        
        for paper in papers:
            if any(author.is_non_academic for author in paper.authors):
                filtered_papers.append(paper)
                
        self._debug_print(f"Filtered {len(filtered_papers)} papers with pharmaceutical/biotech authors")
        return filtered_papers

    def export_to_csv(self, papers: List[Paper], file: Union[str, TextIO]) -> None:
        """Export paper information to a CSV file.
        
        Args:
            papers: A list of Paper objects to export.
            file: A filename or file-like object to write to.
        """
        fieldnames = [
            "PubmedID", 
            "Title", 
            "Publication Date", 
            "Non-academic Author(s)", 
            "Company Affiliation(s)", 
            "Corresponding Author Email"
        ]
        
        close_file = False
        if isinstance(file, str):
            file_obj = open(file, 'w', newline='', encoding='utf-8')
            close_file = True
        else:
            file_obj = file
            
        try:
            writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
            writer.writeheader()
            
            for paper in papers:
                non_academic_authors = "; ".join(author.name for author in paper.non_academic_authors)
                company_affiliations = "; ".join(paper.company_affiliations)
                
                writer.writerow({
                    "PubmedID": paper.pubmed_id,
                    "Title": paper.title,
                    "Publication Date": paper.publication_date,
                    "Non-academic Author(s)": non_academic_authors,
                    "Company Affiliation(s)": company_affiliations,
                    "Corresponding Author Email": paper.corresponding_author_email or ""
                })
                
        finally:
            if close_file:
                file_obj.close()
                
    def get_papers_with_pharma_authors(self, query: str) -> List[Paper]:
        """Get papers with pharmaceutical/biotech authors based on a query.
        
        Args:
            query: The search query in PubMed syntax.
            
        Returns:
            A list of Paper objects with pharmaceutical/biotech authors.
        """
        paper_ids = self.search_papers(query)
        papers = self.fetch_paper_details(paper_ids)
        filtered_papers = self.filter_papers_with_pharma_authors(papers)
        
        return filtered_papers


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments.
    
    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Fetch papers from PubMed with authors affiliated with pharmaceutical/biotech companies."
    )
    
    parser.add_argument(
        "query",
        help="Search query in PubMed syntax"
    )
    
    parser.add_argument(
        "-d", "--debug",
        action="store_true",
        help="Print debug information during execution"
    )
    
    parser.add_argument(
        "-f", "--file",
        help="Specify the filename to save the results. If not provided, print to console."
    )
    
    return parser.parse_args()


def main() -> int:
    """Main function to run the program.
    
    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    args = parse_arguments()
    
    # Initialize the PubMed fetcher
    fetcher = PubMedFetcher(debug=args.debug)
    
    try:
        # Get papers with pharmaceutical/biotech authors
        filtered_papers = fetcher.get_papers_with_pharma_authors(args.query)
        
        # Export the results
        if args.file:
            fetcher.export_to_csv(filtered_papers, args.file)
            if args.debug:
                print(f"[DEBUG] Results saved to {args.file}", file=sys.stderr)
        else:
            # Print to console
            fetcher.export_to_csv(filtered_papers, sys.stdout)
            
        return 0
        
    except Exception as e:
        if args.debug:
            print(f"[ERROR] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())