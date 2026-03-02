import sys
sys.path.append('..')
from orchestration import *
import argparse

def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='Ingest a project using property and knowledge graphs with a vector store.')
    parser.add_argument('--project-path', required=True, help='Path to the project directory to ingest')
    parser.add_argument('--data-store', required=True, help='Directory where the data store should be written')
    parser.add_argument('--project-name', required=True, help='Name of the project (used in IRIs)')
    parser.add_argument('--query', help='Optional prompt to query after ingestion')
    parser.add_argument('--top-k', type=int, default=5, help='Number of results to return for queries')
    args = parser.parse_args(argv)
    ingestor = Ingestor(args.project_path, args.data_store, args.project_name)
    ingestor.ingest()
    print(f"Ingestion complete. Data store created at {args.data_store}")
    if args.query:
        results = ingestor.query(args.query, args.top_k)
        print('Top matches:')
        for h, score in results['top_k']:
            print(f"  {h}: {score:.3f}")
        print('\nProperty nodes:')
        for node in results['property_nodes']:
            print(f"  {node}")
        print('\nKnowledge triples:')
        for triple in results['knowledge_triples']:
            print(f"  {triple}")
    return 0