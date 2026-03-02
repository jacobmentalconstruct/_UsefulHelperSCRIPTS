# **Tri-State Topological Cartridge (TSTC)**

The **Tri-State Topological Cartridge** is a deterministic framework for context-aware data retrieval and automated software assembly. It replaces probabilistic "hallucination-prone" generation with a multi-layered topological assembly engine.  
This system decomposes source code and documentation into three interlocking layers of reality:

1. **Verbatim (The Body):** Immutable, content-addressable source code (SHA256 hashed).  
2. **Semantic (The Skeleton):** A property graph and RDF knowledge graph defining logical relationships (dependencies, inheritance, authorship).  
3. **Vector (The Soul):** High-dimensional embeddings (Doc2Vec) that map natural language intent to specific topological entry points.

## **Project Structure**

* tristate\_ingestor.py: The core CLI tool for ingesting codebases into the Tri-State data store.  
* micro\_stamper.py: A Tkinter-based "Microservice Factory" for atomizing scripts into WASM-wrapped serverless units.  
* requirements.txt: Project dependencies.  
* manifests/: Directory containing JSON/RDF snapshots of the project's topology.

## **Installation**

Ensure you have Python 3.8+ installed.

1. **Clone the repository and enter the directory.**  
2. **Install dependencies:**  
   pip install \-r requirements.txt

3. **WASM Support (Optional):** To compile the stamped microservices, install the [Rust toolchain](https://rustup.rs/) and wasm-pack.

## **Usage: CLI Ingestor**

The CLI ingestor processes a project directory and builds the Tri-State Cartridge.

### **Basic Ingestion**

python tristate\_ingestor.py \--project-path ./my\_codebase \--data-store ./cartridge\_out \--project-name "MyProject"

### **Ingestion with Knowledge Graph Query**

If using the neural-ingestion.py variant, you can query the latent space immediately after ingestion:  
python neural-ingestion.py \--project-path ./src \--data-store ./output \--project-name "Alpha" \--query "How do I authenticate users?"

### **CLI Arguments**

| Argument | Description |
| :---- | :---- |
| \--project-path | Path to the source code or text files to ingest. |
| \--data-store | Directory where the Verbatim, Semantic, and Vector layers will be saved. |
| \--project-name | Identifier used for RDF namespaces and manifest metadata. |
| \--query | (Optional) A natural language prompt to test the vector-to-graph retrieval. |

## **Usage: Microservice Factory (GUI)**

The micro\_stamper.py utility provides a visual interface to "slice" your Python logic into standalone, serverless-ready microservices.

### **Launching the Factory**

python micro\_stamper.py

### **Steps to "Stamp" Microservices:**

1. **Browse:** Click 'BROWSE' to select a Python script you wish to atomize.  
2. **Run Factory:** The tool uses AST (Abstract Syntax Tree) to identify functional blocks and classes.  
3. **Monitor:** The log viewer provides real-time updates on AST slicing and WASM boilerplate generation.  
4. **Retrieve:** Stamped services are output to the stamped\_services/ directory, each containing its verbatim logic, a Rust/WASM wrapper, and a semantic manifest.

## **The Tri-State Logic Flow**

When you prompt an orchestrator built on this cartridge, the following deterministic cycle occurs:

1. **Vector Anchoring:** Your prompt (e.g., "build a login flow") is embedded and mapped to the closest code hashes.  
2. **Semantic Expansion:** The system follows the graph "wires" to pull in every dependency (e.g., DB connectors, hashing utilities) required by those hashes.  
3. **Verbatim Assembly:** The orchestrator retrieves the exact, immutable code blocks from the Content-Addressable Store (CAS) and assembles the final application.

## **License**

MIT License \- Created for the future of deterministic AI engineering.