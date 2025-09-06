# rag_setup.py
import os
import json
from datetime import datetime

from dotenv import load_dotenv
from langchain.text_splitter import MarkdownHeaderTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

load_dotenv(override=True)

vector_store = None
TIMESTAMP_FILE = "rag_timestamp.json"


def get_file_mtime(file_path):
    """Get file modification time"""
    if os.path.exists(file_path):
        return os.path.getmtime(file_path)
    return 0


def load_timestamp():
    """Load timestamp of last embedding"""
    if os.path.exists(TIMESTAMP_FILE):
        try:
            with open(TIMESTAMP_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("last_embedding_time", 0)
        except:
            return 0
    return 0


def save_timestamp():
    """Save current timestamp"""
    with open(TIMESTAMP_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_embedding_time": datetime.now().timestamp()}, f)


def needs_re_embedding(markdown_path):
    """Check if re-embedding is needed"""
    if not vector_store:
        return True
    
    file_mtime = get_file_mtime(markdown_path)
    last_embedding_time = load_timestamp()
    
    return file_mtime > last_embedding_time


def setup_rag():
    global vector_store

    # Knowledge base file path - read from environment variable, default to relative path
    markdown_path = os.getenv("KNOWLEDGE_BASE_PATH", "docs/Museum_Collection_Info.md")

    if not os.path.exists(markdown_path):
        print(f"Error: Knowledge base file not found {markdown_path}")
        print(f"Please ensure the file path is correct, or set KNOWLEDGE_BASE_PATH environment variable")
        # Create empty vector store to avoid program crash
        vector_store = None
        return
    
    # Check if re-embedding is needed
    if not needs_re_embedding(markdown_path):
        print("📄 Knowledge base file not updated, skipping embedding process")
        return

    try:
        with open(markdown_path, "r", encoding="utf-8") as f:
            markdown_document = f.read()

        if not markdown_document.strip():
            print(f"Warning: Knowledge base file {markdown_path} is empty")
            vector_store = None
            return

        # 1. Define which Markdown headers to split on
        headers_to_split_on = [
            ("#", "Header 1"),
            ("##", "Header 2"),
            ("###", "Header 3"),
        ]

        # 2. Instantiate Markdown splitter
        markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=headers_to_split_on
        )
        md_header_splits = markdown_splitter.split_text(markdown_document)

        if not md_header_splits:
            print(f"Warning: Unable to extract any document fragments from {markdown_path}")
            vector_store = None
            return

        # 3. Build embeddings and vector storage
        # LangChain's FAISS.from_documents automatically handles Document objects
        print("🔄 Rebuilding vector storage...")
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        vector_store = FAISS.from_documents(md_header_splits, embeddings)
        
        # Save timestamp
        save_timestamp()
        print("✅ RAG system successfully initialized (using Markdown splitting)!")
        
    except FileNotFoundError:
        print(f"Error: Unable to read knowledge base file {markdown_path}")
        vector_store = None
    except UnicodeDecodeError:
        print(f"Error: Knowledge base file {markdown_path} has incorrect encoding format")
        vector_store = None
    except Exception as e:
        print(f"Error: Unexpected error occurred while initializing RAG system: {e}")
        vector_store = None


# search_knowledge_base function remains unchanged
def search_knowledge_base(query: str) -> str:
    global vector_store
    if not vector_store:
        return "Knowledge base not yet initialized."

    retriever = vector_store.as_retriever(search_kwargs={"k": 3})  # Increase retrieval count to handle comparison questions
    relevant_docs = retriever.invoke(query)

    context = "\n\n---\n\n".join(
        [
            f"Source: {doc.metadata.get('Header 2', '')} > {doc.metadata.get('Header 3', '')}\nContent: {doc.page_content}"
            for doc in relevant_docs
        ]
    )
    return f"Relevant information found in knowledge base:\n{context}"
