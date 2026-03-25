# Knowledge Orchestrator

Strategic knowledge management and cross-project information synthesis.

## Purpose

The `knowledge-orchestrator` acts as a high-level librarian for the Agent OS. It goes beyond simple RAG by actively synthesizing information across different project silos, identifying missing links in the knowledge base, and generating summary reports for the user.

## Key Features

- **Cross-Project RAG**: Aggregates context from multiple session histories and skill repositories.
- **Hypothesis Generator**: Identifies gaps in local knowledge and proposes "Research Tasks" for the user or other agents.
- **Automatic Documentation**: Generates and updates architecture diagrams and API docs (like these) based on code analysis.
- **Knowledge Graph Integration**: Maps entity relationships extracted from unstructured notes.

## Usage

```bash
python main.py --project knowledge-orchestrator --task synthesize-all
```
