import sys
import os
import time
import json

# Fix path so we can import src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from microservices.cartridge_service import CartridgeService
from microservices.neural_service import NeuralService
from microservices.intake_service import IntakeService
from microservices.refinery_service import RefineryService

TEST_DB = "tests/test_cartridge.db"
TEST_SOURCE_DIR = "tests/dummy_source"

def setup_dummy_data():
    if not os.path.exists(TEST_SOURCE_DIR):
        os.makedirs(TEST_SOURCE_DIR)
    
    # Create a text file with specific distinct concepts
    with open(f"{TEST_SOURCE_DIR}/concept.txt", "w") as f:
        f.write("""
        Project: Project Necromancy.
        Objective: To resurrect dead code using AI patches.
        Lead Engineer: Jacob Lambert.
        Tools: _RagFORGE, _TokenizingPATCHER.
        Status: ACTIVE.
        """)
    print("[TEST] Dummy data created.")

def run_test():
    # 1. Cleanup old test
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

    setup_dummy_data()

    print(f"[TEST] Forging Cartridge: {TEST_DB}")
    
    # 2. Initialize Services
    cartridge = CartridgeService(TEST_DB)
    neural = NeuralService()
    intake = IntakeService(cartridge)
    refinery = RefineryService(cartridge, neural)

    # 3. Intake Phase
    print(">>> Phase 1: Intake")
    # Using the new ingest_source method we patched
    stats = intake.ingest_source(TEST_SOURCE_DIR)
    print(f"    Stats: {stats}")

    # 4. Refinery Phase
    print(">>> Phase 2: Refinery")
    processed = refinery.process_pending(batch_size=10)
    print(f"    Refined {processed} files.")
    
    # Allow DB to settle
    time.sleep(1)

    # 5. Verification: Manifest
    print("\n[VERIFY] Checking Manifest...")
    cid = cartridge.get_manifest("cartridge_id")
    schema = cartridge.get_manifest("schema_version")
    print(f"    Cartridge ID: {cid}")
    print(f"    Schema Ver:   {schema}")
    
    if not cid:
        print("    [FAIL] Manifest missing!")
        return

    # 6. Verification: Vector Search
    print("\n[VERIFY] Testing Vector Search...")
    # We search for a concept that shouldn't match by keyword alone but works semantically
    query = "Who is the lead engineer?" 
    print(f"    Query: '{query}'")
    
    q_vec = neural.get_embedding(query)
    results = cartridge.search_embeddings(q_vec, limit=1)
    
    if results:
        top = results[0]
        print(f"    [SUCCESS] Match found!")
        print(f"    Score: {top['score']}")
        print(f"    Content: {top['content'].strip()}")
    else:
        print("    [FAIL] No vector results found. Is sqlite-vec working?")

if __name__ == "__main__":
    try:
        run_test()
    except Exception as e:
        print(f"[FATAL] Test failed: {e}")
