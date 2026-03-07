# ============================================================
# DocuMind - Module 6: MCP Server
# 
# This file creates an MCP server that exposes DocuMind's
# RAG capabilities as TOOLS that any MCP client can use.
# 
# main.py = the web app (humans use via browser)
# mcp_server.py = the plugin (AI agents use via MCP)
# ============================================================

# --- MCP SDK ---
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# --- Standard libraries ---
import asyncio
import json
import os

# --- Our existing tools ---
from dotenv import load_dotenv
import chromadb
from sentence_transformers import SentenceTransformer
import fitz
import uuid
import anthropic

# ------------------------------------------------------------
# IMPORTANT: Use absolute paths
# 
# When Claude Desktop launches this server, the working
# directory might not be your project folder. Relative paths
# like "./chroma_data" would point to the wrong location.
# Absolute paths always work regardless of where the server
# is launched from.
# ------------------------------------------------------------
PROJECT_DIR = "/Users/mayowababatola/Apps/documind"

# Load environment variables using absolute path
load_dotenv(f"{PROJECT_DIR}/.env")

# ------------------------------------------------------------
# Initialize embedding model and ChromaDB
# ------------------------------------------------------------
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

# Use absolute path so ChromaDB finds the same database
# that main.py uses, no matter where this script is run from
chroma_client = chromadb.PersistentClient(path=f"{PROJECT_DIR}/chroma_data")
collection = chroma_client.get_or_create_collection(
    name="documents",
    metadata={"hnsw:space": "cosine"}
)

# Anthropic client for RAG answers
ai_client = anthropic.Anthropic()

# ------------------------------------------------------------
# Helper functions (same logic as main.py)
# ------------------------------------------------------------

def search_chunks(query: str, top_k: int = 3) -> list[dict]:
    """Search ChromaDB for relevant chunks."""
    query_embedding = embedding_model.encode(query).tolist()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k
    )
    matches = []
    if results["documents"][0]:
        for doc, metadata, distance in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0]
        ):
            matches.append({
                "text": doc,
                "page": metadata["page"],
                "document_id": metadata["document_id"],
                "distance": distance
            })
    return matches


def rag_answer(question: str) -> dict:
    """Full RAG pipeline: search + Claude answer."""
    # Retrieve
    relevant_chunks = search_chunks(question, top_k=3)
    
    # Augment
    if relevant_chunks:
        context_parts = []
        for i, chunk in enumerate(relevant_chunks, start=1):
            context_parts.append(
                f"Source {i} (Page {chunk['page']}):\n{chunk['text']}"
            )
        context = "\n\n".join(context_parts)
        
        user_message = f"""Based on the following document excerpts, answer the question.
If the excerpts don't contain enough information, say so and answer from general knowledge.
Always cite which source(s) you used.

DOCUMENT EXCERPTS:
{context}

QUESTION: {question}"""
    else:
        user_message = f"""No relevant documents were found for this question.
Please answer from general knowledge and mention that no documents were available.

QUESTION: {question}"""
    
    # Generate
    message = ai_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system="You are DocuMind, an AI assistant. When given document excerpts, base your answers on them and cite your sources. Be concise and accurate.",
        messages=[{"role": "user", "content": user_message}]
    )
    
    return {
        "answer": message.content[0].text,
        "sources": relevant_chunks,
        "model": message.model
    }


# ============================================================
# CREATE THE MCP SERVER
# ============================================================
server = Server("documind")


# ------------------------------------------------------------
# REGISTER TOOLS
# ------------------------------------------------------------

@server.list_tools()
async def list_tools() -> list[Tool]:
    """Tell MCP clients what tools DocuMind offers."""
    return [
        Tool(
            name="search_documents",
            description="Search uploaded documents for relevant content. Use this when you need to find specific information in the document collection. Returns the most relevant text chunks with page numbers and similarity scores.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query - what you want to find in the documents"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default: 3)",
                        "default": 3
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="ask_question",
            description="Ask a question and get an AI-powered answer based on uploaded documents. Uses RAG (Retrieval-Augmented Generation) to find relevant document sections and generate an accurate, cited answer.",
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The question to answer based on the documents"
                    }
                },
                "required": ["question"]
            }
        ),
        Tool(
            name="list_documents",
            description="List all documents currently stored in the system. Returns the total count of documents and text chunks available for searching.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool execution when an AI agent calls a tool."""
    
    if name == "search_documents":
        query = arguments["query"]
        top_k = arguments.get("top_k", 3)
        results = search_chunks(query, top_k=top_k)
        
        return [TextContent(
            type="text",
            text=json.dumps({
                "query": query,
                "results": results,
                "count": len(results)
            }, indent=2)
        )]
    
    elif name == "ask_question":
        question = arguments["question"]
        result = rag_answer(question)
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
    
    elif name == "list_documents":
        count = collection.count()
        
        return [TextContent(
            type="text",
            text=json.dumps({
                "total_chunks": count,
                "database_path": f"{PROJECT_DIR}/chroma_data",
                "status": "active"
            }, indent=2)
        )]
    
    else:
        return [TextContent(
            type="text",
            text=json.dumps({"error": f"Unknown tool: {name}"})
        )]


# ============================================================
# MAIN ENTRY POINT
# ============================================================

async def main():
    """Start the MCP server using stdio transport."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())