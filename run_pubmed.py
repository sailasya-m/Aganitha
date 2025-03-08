import argparse
from punmed_fetcher.punmed_fetcher import PubMedFetcher  # Ensure the correct import

def main():
    parser = argparse.ArgumentParser(description="Fetch PubMed papers with pharma/biotech authors.")
    parser.add_argument("query", help="Search query for PubMed")
    parser.add_argument("-f", "--file", help="Output CSV filename", default="results.csv")

    args = parser.parse_args()
    
    # Initialize the fetcher
    fetcher = PubMedFetcher(debug=True)

    # Get papers with pharmaceutical/biotech authors
    papers = fetcher.get_papers_with_pharma_authors(args.query)

    # Export results
    fetcher.export_to_csv(papers, args.file)

    print(f"Results saved to {args.file}")

# Ensure the script runs only when executed directly
if __name__ == "__main__":
    main()
