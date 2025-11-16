import os
import faiss
from typing import List, Tuple
from dotenv import load_dotenv


# LangChain Imports
from langchain.chat_models import init_chat_model
from langchain.tools import tool
from langchain.agents import create_agent
from langchain_openai import AzureOpenAIEmbeddings
from langchain_community.document_loaders import WebBaseLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.embeddings import Embeddings
from langchain_core.messages import BaseMessage


load_dotenv()
# --- Configuration Constants ---
# It's better practice to read from environment variables directly inside the functions
# or pass them as arguments, but keeping them here for easy modification.
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_API_VERSION = "2024-12-01-preview"
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = "text-embedding-3-small"
AZURE_OPENAI_CHAT_DEPLOYMENT = "gpt-4o"

# Set environment variables (optional if already set in the shell)
os.environ["AZURE_OPENAI_API_KEY"] = AZURE_OPENAI_API_KEY
os.environ["AZURE_OPENAI_ENDPOINT"] = AZURE_OPENAI_ENDPOINT
os.environ["OPENAI_API_VERSION"] = AZURE_OPENAI_API_VERSION


# --- Initialization Functions ---


def initialize_chat_model() -> BaseChatModel:
    """Initializes and returns the Azure OpenAI Chat Model."""
    print(f"Initializing Chat Model: {AZURE_OPENAI_CHAT_DEPLOYMENT}")
    model = init_chat_model(
        "azure_openai:gpt-4o",
        azure_deployment=AZURE_OPENAI_CHAT_DEPLOYMENT,
        # Ensure correct API version is used
        openai_api_version=AZURE_OPENAI_API_VERSION,
    )
    return model


def initialize_embeddings() -> AzureOpenAIEmbeddings:
    """Initializes and returns the Azure OpenAI Embeddings model."""
    print(f"Initializing Embeddings Model: {AZURE_OPENAI_EMBEDDING_DEPLOYMENT}")
    embeddings = AzureOpenAIEmbeddings(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_API_KEY,  # type: ignore
        api_version=AZURE_OPENAI_API_VERSION,
        azure_deployment=AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
    )
    return embeddings


def initialize_empty_vector_db(embeddings: Embeddings) -> FAISS:
    """
    Initializes and returns an empty FAISS vector store.

    Args:
        embeddings: The embeddings model to use for the vector store.
    """
    print("Initializing empty FAISS Vector Store.")
    # Calculate embedding dimension to initialize FAISS index
    embedding_dim = len(embeddings.embed_query("dummy text"))
    index = faiss.IndexFlatL2(embedding_dim)

    vector_store = FAISS(
        embedding_function=embeddings,
        index=index,
        docstore=InMemoryDocstore(),
        index_to_docstore_id={},
    )
    return vector_store


# --- Data Loading and Processing Functions ---


def load_documents_from_urls(urls: List[str]) -> List[Document]:
    """Loads documents from a list of URLs using WebBaseLoader."""
    print(f"Loading documents from {len(urls)} URLs...")
    loader = WebBaseLoader(urls)
    docs = loader.load()
    print(f"Successfully loaded {len(docs)} documents.")
    return docs


def chunk_documents(
    docs: List[Document], chunk_size: int = 1000, chunk_overlap: int = 200
) -> List[Document]:
    """Splits documents into smaller chunks."""
    print(f"Chunking documents (size={chunk_size}, overlap={chunk_overlap})...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        add_start_index=True,
    )
    all_splits = text_splitter.split_documents(docs)
    print(f"Split documents into {len(all_splits)} chunks.")
    return all_splits


# --- Vector Database Operations ---


def save_vector_db(vector_store: FAISS, path: str = "faiss_index"):
    """Saves the FAISS vector store locally."""
    print(f"Saving vector store to '{path}'...")
    vector_store.save_local(path)
    print("Vector store saved.")


def load_vector_db(embeddings: Embeddings, path: str = "faiss_index") -> FAISS:
    """Loads a FAISS vector store from a local directory."""
    print(f"Loading vector store from '{path}'...")
    # NOTE: allow_dangerous_deserialization=True is required for unpickling
    vector_store = FAISS.load_local(
        path, embeddings, allow_dangerous_deserialization=True
    )
    print("Vector store loaded.")
    return vector_store


def create_and_save_vector_db(
    docs: List[Document], embeddings: Embeddings, path: str = "faiss_index"
) -> FAISS:
    """Creates a new FAISS vector store from documents and saves it."""
    # 1. Initialize an empty DB
    vector_store = initialize_empty_vector_db(embeddings)

    # 2. Add documents
    print(f"Adding {len(docs)} document chunks to the vector store...")
    # The FAISS object will build the index when documents are added
    document_ids = vector_store.add_documents(documents=docs)
    print(f"Added documents. First ID: {document_ids[0]}")

    # 3. Save the DB
    save_vector_db(vector_store, path)
    return vector_store


# --- Query and Retrieval Functions ---


def define_retrieval_tool(vector_store: FAISS):
    """
    Defines and returns the retrieval tool function.

    This function must be defined *inside* another function or made a closure
    to capture the `vector_store` object, as LangChain's `@tool` decorator
    expects a standalone function or method.
    """

    @tool(response_format="content_and_artifact")
    def retrieve_context(query: str) -> Tuple[str, List[Document]]:
        """Retrieve information to help answer a query."""
        print(f"Retrieving context for query: '{query[:50]}...'")
        retrieved_docs = vector_store.similarity_search(query, k=10)
        serialized = "\n\n".join(
            (
                f"Source: {doc.metadata.get('source', 'Unknown')}\nContent: {doc.page_content}"
            )
            for doc in retrieved_docs
        )
        return serialized, retrieved_docs

    return retrieve_context


def create_rag_agent(model: BaseChatModel, tools, system_prompt: str):
    """Creates and returns the LangChain RAG agent."""
    print("Creating RAG Agent...")
    agent = create_agent(model, tools, system_prompt=system_prompt)
    return agent


def get_agent_response(agent, query: str):
    """Streams the response from the agent for a given query."""
    print(f"\n--- Getting Response for Query ---\nQuery: {query}")
    for event in agent.stream(
        {"messages": [{"role": "user", "content": query}]},
        stream_mode="values",
    ):
        event["messages"][-1].pretty_print()
    print("\n--- Response Complete ---")


def get_final_agent_response(agent, query: str) -> str:
    """
    Executes the agent for a query, streams the response internally,
    and returns only the final, concatenated text answer.
    """
    print(f"\n--- Starting Agent Execution ---\nQuery: {query}")

    final_response_parts = []

    # Iterate through the stream of events
    for event in agent.stream(
        {"messages": [{"role": "user", "content": query}]},
        stream_mode="values",
    ):
        # LangGraph/Agent Executor stream returns a dictionary with 'messages'
        # The last message in the list is the current one being processed/streamed

        last_message: BaseMessage = event["messages"][-1]

        # Check if the message is the final 'content' from the AI model (Role: 'assistant')
        # The content could be split across multiple streamed events
        if last_message.type == "ai":
            # Append the text content of the message
            # The .content is often a string, but can be a list if it contains tools calls/results
            if isinstance(last_message.content, str):
                final_response_parts.append(last_message.content)

            # Optional: If you still want to see the streaming output
            # last_message.pretty_print()

    final_answer = "".join(final_response_parts)

    print("\n--- Agent Execution Complete ---")

    # Note: If you want to strip any leading/trailing whitespace/newlines:
    # return final_answer.strip()

    return final_answer


# --- Main Execution Flow ---


def main_execution_flow(
    query: str,
    urls: List[str] = ["www.example.com"],
    db_path: str = "faiss_index",
    force_rebuild_db: bool = False,
):
    """
    Main function to run the RAG process.
    """
    # 1. Initialization
    model = initialize_chat_model()
    embeddings = initialize_embeddings()

    # 2. Vector DB Setup (Load or Create)
    if not force_rebuild_db and os.path.exists(db_path):
        vector_store = load_vector_db(embeddings, db_path)
    else:
        # Load and Chunk Documents
        docs = load_documents_from_urls(urls)
        all_splits = chunk_documents(docs)

        # Create and Save Vector DB
        vector_store = create_and_save_vector_db(all_splits, embeddings, db_path)

    # 3. Agent Setup
    retrieve_context_tool = define_retrieval_tool(vector_store)
    tools = [retrieve_context_tool]
    # prompt = (
    #     "You have access to a tool that retrieves context from financial documents. "
    #     "Use the tool to retrieve relevant information and then answer the user queries concisely."
    # )
    prompt = (
        "You are a financial assistant. Your task is to answer user queries based on a tool you have access to. You MUST adhere to the following rules for EVERY response:\n\n"
        "1.  **No Memory:** You have no memory of previous conversation. Treat every user query as a new, standalone request.\n"
        "2.  **Tool First:** You have a tool that retrieves context from financial documents. You MUST use this tool to find information relevant to the user's query.\n"
        "3.  **NO CLARIFICATIONS:** You are strictly forbidden from asking the user for clarification, more details, or context (e.g., Which year?). If a query is ambiguous, use your tool to find the most relevant or most recent information and present that.\n"
        "4.  **Always Respond:**\n"
        "    * **If Information is Found:** Answer the user's query concisely using *only* the information retrieved from the tool.\n"
        "    * **If No Information is Found:** You MUST respond. Clearly state that the requested information could not be found in the provided documents.\n"
        "5.  **MANDATORY MARKDOWN:** Your *entire* response must be formatted in valid Markdown. Use headings, subheadings, bullet points, tables, blockquotes, or code blocks as necessary to ensure the information is clear, organized, and scannable. Even a simple 'not found' message must be valid Markdown (e.g., `## Information Not Found`)."
    )
    agent = create_rag_agent(model, tools, system_prompt=prompt)

    # return get_agent_response(agent, query)
    return get_final_agent_response(agent, query)


if __name__ == "__main__":
    URLS_TO_LOAD = [
        "https://www.primeloans.kotak.com/chargesFees.htm",
        "https://www.primeloans.kotak.com/grievanceRedressal.htm",
        "https://www.primeloans.kotak.com/investorsDebt.htm",
        "https://www.primeloans.kotak.com/annualReport.htm",
        "https://www.primeloans.kotak.com/policies.htm",
        "https://www.primeloans.kotak.com/media.htm",
        "https://www.primeloans.kotak.com/newCarFinance.htm",
        "https://www.primeloans.kotak.com/usedCarFinance.htm",
        "https://www.primeloans.kotak.com/topUpCarLoan.htm",
        "https://www.primeloans.kotak.com/twoWheeler.htm",
        "https://www.primeloans.kotak.com/carLease.htm",
        "https://www.primeloans.kotak.com/dealerFinance.htm",
        "https://www.primeloans.kotak.com/loanAgainstProperty.htm",
        "https://www.primeloans.kotak.com/carNews.htm",
        "https://www.primeloans.kotak.com/latestCar.htm",
        "https://www.primeloans.kotak.com/upcomingCar.htm",
        "https://www.primeloans.kotak.com/carPrice.htm",
        "https://www.primeloans.kotak.com/compareCars.htm",
        "https://www.primeloans.kotak.com/bikeNews.htm",
        "https://www.primeloans.kotak.com/latestBike.htm",
        "https://www.primeloans.kotak.com/upcomingBike.htm",
        "https://www.primeloans.kotak.com/bikePrice.htm",
        "https://www.primeloans.kotak.com/compareBikes.htm",
        "https://www.primeloans.kotak.com/applyNow.htm",
        "https://www.primeloans.kotak.com/offer.htm",
        "https://www.primeloans.kotak.com/formDownload.htm",
        "https://www.primeloans.kotak.com/document.htm",
        "https://www.primeloans.kotak.com/lifeInsurance.htm",
        "https://www.primeloans.kotak.com/motorInsurance.htm",
        "https://www.primeloans.kotak.com/aboutUs.htm",
        "https://www.primeloans.kotak.com/",
    ]
    # List of URLs to process
    # URLS_TO_LOAD = [
    #     "https://www.primeloans.kotak.com/chargesFees.htm",
    #     "https://www.primeloans.kotak.com/newCarFinance.htm",
    # ]

    # Set force_rebuild_db=True to reload and chunk data from URLs
    query = "What is the Clearing Mandate swap Charges?"
    # query = "What is this Clearing Mandate swap Charges from charge & fees?"
    final_output = main_execution_flow(query, urls=URLS_TO_LOAD, force_rebuild_db=False)
    print(final_output)
