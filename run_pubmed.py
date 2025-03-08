import argparse
from punmed_fetcher.punmed_fetcher import PubMedFetcher  

def main():
    parser = argparse.ArgumentParser(description="Fetch PubMed papers with pharma/biotech authors.")
    parser.add_argument("query", help="Search query for PubMed")
    parser.add_argument("-f", "--file", help="Output CSV filename", default="results.csv")

    args = parser.parse_args()
    

    fetcher = PubMedFetcher(debug=True)

 
    papers = fetcher.get_papers_with_pharma_authors(args.query)


    fetcher.export_to_csv(papers, args.file)

    print(f"Results saved to {args.file}")


if __name__ == "__main__":
    main()
