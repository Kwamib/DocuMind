# DocuMind

**AI-Powered Document Q&A System with RAG, MCP, Angular, and AWS EKS Deployment**

DocuMind is an enterprise-grade document Q&A system that allows users to upload PDFs and ask natural language questions, receiving accurate answers grounded in the uploaded content. It uses Retrieval-Augmented Generation (RAG) to combine vector search with Claude AI for contextual, cited responses.

DocuMind also exposes its capabilities as an MCP (Model Context Protocol) server, making its document search and Q&A tools available to any MCP-compatible AI client — including Claude Desktop, IDE assistants, and custom agents.

---

## Features

- PDF upload and intelligent text extraction
- Document chunking with configurable overlap
- Vector embedding and similarity search via ChromaDB
- RAG-powered Q&A using Anthropic Claude API
- Anti-hallucination guardrails (relevance threshold, confidence scoring, response validation)
- Source citations with each answer
- MCP server exposing document search, Q&A, and listing as tools
- Angular frontend with chat interface and PDF page viewer
- RESTful API with FastAPI and interactive docs
- Docker containerization with multi-stage build
- Kubernetes manifests for AWS EKS deployment
- Modular Terraform infrastructure as code
- CI/CD pipeline with GitHub Actions

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Backend | Python / FastAPI | REST API and orchestration |
| AI / LLM | Anthropic Claude API | Question answering and generation |
| Embeddings | sentence-transformers | Document vectorization (local, no API cost) |
| Vector DB | ChromaDB | Similarity search and retrieval |
| MCP | MCP Python SDK | Tool exposure for AI agent integrations |
| Frontend | Angular | Chat UI, file upload, document viewer |
| Container | Docker | Multi-stage containerized build |
| Orchestration | Kubernetes | Deployment, scaling, health management |
| Infrastructure | Terraform (modular) | ECR, VPC, EKS as code |
| CI/CD | GitHub Actions | Automated build, push, and deploy |

---

## Architecture

```
HUMANS (browser)                    AI AGENTS (Claude Desktop, etc.)
      │                                        │
      │ HTTP requests                          │ MCP protocol
      │                                        │
  ┌───▼────────┐                        ┌──────▼──────┐
  │  Angular   │                        │ MCP Server  │
  │  Frontend  │                        │mcp_server.py│
  │ (port 4200)│                        │  (stdio)    │
  └───┬────────┘                        └──────┬──────┘
      │                                        │
      │                                        │
  ┌───▼────────────────────────────────────────▼──┐
  │              FastAPI Backend                   │
  │              main.py (port 8000)               │
  │                                                │
  │   ┌──────────────────────────────────────┐    │
  │   │         RAG Pipeline                  │    │
  │   │  1. Search ChromaDB for chunks        │    │
  │   │  2. Build prompt with context         │    │
  │   │  3. Send to Claude for answer         │    │
  │   └──────────────────────────────────────┘    │
  └────────────────────────────────────────────────┘
```

---

## Anti-Hallucination Guardrails

DocuMind implements production-grade safeguards to prevent AI hallucination:

- **Relevance Threshold**: Only document chunks with cosine similarity below 0.7 are used. Weak matches are filtered out entirely.
- **Strict System Prompt**: Claude is instructed to answer ONLY from provided documents and cite sources.
- **Low Temperature (0.1)**: Reduces creative/speculative responses in favor of factual, deterministic answers.
- **Confidence Scoring**: Claude rates each answer 1-5. Scores below 3 trigger a warning to the user.
- **Response Validation**: Automated checks verify the answer is grounded in source documents.

---

## Prerequisites

- Python 3.10+
- Node.js 18+ and Angular CLI
- Anthropic API key ([console.anthropic.com](https://console.anthropic.com))
- Docker (for containerization)
- AWS CLI configured (for deployment)

---

## Quick Start

### 1. Clone and Set Up Environment

```bash
git clone https://github.com/Kwamib/DocuMind.git
cd DocuMind
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### 3. Run the Backend

```bash
uvicorn main:app --reload --port 8000
```

### 4. Run the Frontend (Development)

```bash
cd frontend
npm install
ng serve
```

Open http://localhost:4200

### 5. Run with Docker (Production)

```bash
docker build -t documind .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=your-key-here documind
```

Open http://localhost:8000

### 6. Run the MCP Server (for Claude Desktop)

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "documind": {
      "command": "/path/to/venv/bin/python",
      "args": ["/path/to/mcp_server.py"],
      "cwd": "/path/to/documind"
    }
  }
}
```

---

## Project Structure

```
documind/
├── main.py                  # FastAPI backend (RAG pipeline, API endpoints)
├── mcp_server.py            # MCP server (AI agent integration)
├── Dockerfile               # Multi-stage Docker build
├── .dockerignore             # Files excluded from Docker builds
├── .env                     # API keys (not committed)
├── .gitignore               # Git exclusions
├── requirements.txt         # Python dependencies
├── frontend/                # Angular application
│   └── src/
│       └── app/
│           └── chat/        # Chat component with document viewer
├── k8s/                     # Kubernetes manifests
│   ├── deployment.yaml      # Pod deployment configuration
│   ├── service.yaml         # Load balancer service
│   ├── secrets.yaml         # API key secrets (not committed)
│   └── storage.yaml         # Persistent volume claims
├── terraform/               # Infrastructure as code (modular)
│   ├── main.tf              # Root module
│   ├── variables.tf         # Input variables
│   ├── outputs.tf           # Output values
│   ├── modules/
│   │   ├── ecr/             # Container registry module
│   │   ├── vpc/             # Network infrastructure module
│   │   └── eks/             # Kubernetes cluster module
│   └── environments/
│       ├── dev.tfvars       # Dev environment config
│       └── prod.tfvars      # Prod environment config
└── .github/
    └── workflows/
        └── deploy.yml       # CI/CD pipeline
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/upload | Upload a PDF document |
| POST | /api/ask | Ask a question (RAG pipeline) |
| POST | /api/search | Search documents by meaning |
| GET | /api/documents | List all uploaded documents |
| GET | /api/documents/{id}/download | Download original PDF |
| GET | /api/documents/{id}/pages/{num} | View a PDF page as image |
| GET | /api/documents/{id}/chunks | View document chunks |
| DELETE | /api/documents/{id} | Delete a document |
| GET | /api/health | Health check with system stats |

---

## MCP Tools

When running as an MCP server, DocuMind exposes these tools:

| Tool | Description |
|------|-------------|
| search_documents | Search uploaded docs by semantic similarity |
| ask_question | RAG-powered Q&A with citations |
| list_documents | List all documents and chunk counts |

---

## Deployment

### AWS EKS with Terraform

```bash
cd terraform
terraform init
terraform plan -var-file=environments/dev.tfvars
terraform apply -var-file=environments/dev.tfvars
```

### Push Docker Image to ECR

```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com
docker tag documind:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/documind:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/documind:latest
```

### Deploy to Kubernetes

```bash
aws eks update-kubeconfig --region us-east-1 --name documind-cluster
kubectl apply -f k8s/secrets.yaml
kubectl apply -f k8s/storage.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

---

## License

MIT License
