import os, tempfile
import streamlit as st
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

st.set_page_config(page_title="DocuChat RAG", page_icon="📄", layout="wide")

# ---------- Custom theme (CSS) ----------
st.markdown("""
<style>
:root {
    --primary: #4F46E5;
    --primary-dark: #3730A3;
    --accent: #06B6D4;
    --bg: #F4F6FB;
    --card: #FFFFFF;
    --text: #1F2937;
    --muted: #6B7280;
}

/* Hide default Streamlit chrome for a real-website look */
#MainMenu, footer, header[data-testid="stToolbar"] {visibility: hidden;}

/* Page background and text */
.stApp {background: var(--bg);}
.stApp, .stApp p, .stApp label, .stApp span, .stApp li {color: var(--text);}
.block-container {padding-top: 4rem; max-width: 1100px;}
header[data-testid="stHeader"] {background: transparent;}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: #EEF0FF;
    border-right: 1px solid #DDE1FF;
}
section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3 {
    color: var(--primary-dark);
}

/* Hero banner */
.hero {
    background: linear-gradient(120deg, #4F46E5 0%, #7C3AED 55%, #06B6D4 100%);
    padding: 2.2rem 2.5rem;
    border-radius: 18px;
    margin-bottom: 1.5rem;
    box-shadow: 0 10px 30px rgba(79, 70, 229, 0.25);
}
.stApp .hero h1, .stApp .hero h1 span {color: #FFFFFF !important; margin: 0; font-size: 2.2rem;}
.hero p {color: #E0E7FF !important; margin: 0.4rem 0 0 0; font-size: 1.05rem;}

/* Feature cards */
.card {
    background: var(--card);
    padding: 1.4rem;
    border-radius: 14px;
    border: 1px solid #E5E7EB;
    box-shadow: 0 4px 14px rgba(17, 24, 39, 0.06);
    height: 100%;
    min-height: 190px;
}
.card h3 {color: var(--primary) !important; margin: 0 0 0.4rem 0; font-size: 1.15rem;}
.card p {color: var(--muted) !important; margin: 0;}

/* Chat messages */
div[data-testid="stChatMessage"] {
    background: var(--card);
    border: 1px solid #E5E7EB;
    border-radius: 14px;
    padding: 1rem 1.2rem;
    box-shadow: 0 2px 8px rgba(17, 24, 39, 0.05);
    margin-bottom: 0.8rem;
}

/* Buttons */
.stButton > button {
    background: var(--primary);
    color: #FFFFFF;
    border: none;
    border-radius: 10px;
    font-weight: 600;
}
.stButton > button:hover {background: var(--primary-dark); color: #FFFFFF;}
.stButton > button p {color: #FFFFFF !important;}

/* Slider handle */
div[data-baseweb="slider"] div[role="slider"] {background-color: var(--primary) !important;}

/* Expander */
div[data-testid="stExpander"] {
    background: #FAFAFF;
    border: 1px solid #E0E7FF;
    border-radius: 10px;
}
</style>
""", unsafe_allow_html=True)

# ---------- Sidebar ----------
with st.sidebar:
    st.header("⚙️ Settings")

    env_key = os.getenv("GROQ_API_KEY")
    if env_key:
        api_key = env_key
        st.success("Groq API key loaded ✅")
    else:
        api_key = st.text_input("Groq API Key", type="password")

    pdf = st.file_uploader("Upload a PDF", type="pdf")

    st.subheader("RAG parameters")
    chunk_size = st.slider("Chunk size", 200, 2000, 800, step=100)
    chunk_overlap = st.slider("Chunk overlap", 0, 500, 100, step=50)
    top_k = st.slider("Chunks to retrieve (k)", 1, 6, 3)

    if st.button("🗑️ Clear chat", use_container_width=True):
        st.session_state.history = []
        st.rerun()

# ---------- Hero ----------
st.markdown("""
<div class="hero">
    <h1>📄 DocuChat</h1>
    <p>Ask questions about any PDF. Powered by LangChain, FAISS and Groq.</p>
</div>
""", unsafe_allow_html=True)

# ---------- Cached resources ----------
@st.cache_resource(show_spinner="Loading embedding model...")
def get_embeddings():
    return HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

@st.cache_resource(show_spinner="Reading PDF and building FAISS index...")
def build_index(file_bytes: bytes, chunk_size: int, chunk_overlap: int):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
        f.write(file_bytes)
        path = f.name
    docs = PyPDFLoader(path).load()                                   # 1. load
    os.remove(path)

    # Scanned PDFs (e.g. CamScanner) have almost no real text, only a watermark
    real_text = " ".join(d.page_content for d in docs).replace("CamScanner", "")
    if len(real_text.strip()) < 50 * len(docs):
        return None, len(docs), 0

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=min(chunk_overlap, chunk_size - 1))
    chunks = splitter.split_documents(docs)                           # 2. chunk
    db = FAISS.from_documents(chunks, get_embeddings())               # 3. embed + store
    return db, len(docs), len(chunks)

prompt = ChatPromptTemplate.from_template(
    "Answer ONLY from the context below. If the answer is not in the context, say "
    "'I could not find this in the document.'\n\nContext:\n{context}\n\nQuestion: {question}")

if "history" not in st.session_state:
    st.session_state.history = []

# ---------- Welcome screen ----------
if not (api_key and pdf):
    st.info("👈 Add your Groq API key and upload a PDF in the sidebar to get started.")
    c1, c2, c3 = st.columns(3)
    c1.markdown('<div class="card"><h3>1️⃣ Upload</h3><p>Upload any PDF from the sidebar.</p></div>',
                unsafe_allow_html=True)
    c2.markdown('<div class="card"><h3>2️⃣ Index</h3><p>The app splits it into chunks and stores embeddings in FAISS.</p></div>',
                unsafe_allow_html=True)
    c3.markdown('<div class="card"><h3>3️⃣ Ask</h3><p>Ask questions and get answers with source pages.</p></div>',
                unsafe_allow_html=True)
    st.stop()

# ---------- Build index ----------
db, n_pages, n_chunks = build_index(pdf.getvalue(), chunk_size, chunk_overlap)
if db is None:
    st.error("This PDF has no readable text (it looks like a scanned image). "
             "Please upload a text-based PDF, for example one saved from Word or Google Docs.")
    st.stop()
st.sidebar.success(f"{n_pages} pages, {n_chunks} chunks indexed")
retriever = db.as_retriever(search_kwargs={"k": top_k})               # 4. retriever
llm = ChatGroq(model="openai/gpt-oss-20b", api_key=api_key, temperature=0)  # 5. LLM

# ---------- Show chat history ----------
for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        st.write(msg["text"])
        if msg.get("sources"):
            with st.expander("📚 Sources"):
                for i, (page, text) in enumerate(msg["sources"], 1):
                    st.markdown(f"**Chunk {i}**, page {page}")
                    st.write(text)

# ---------- New question ----------
if q := st.chat_input("Ask a question about your document..."):
    st.chat_message("user").write(q)
    st.session_state.history.append({"role": "user", "text": q})

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            hits = retriever.invoke(q)
            ctx = "\n\n".join(h.page_content for h in hits)
            ans = (prompt | llm).invoke({"context": ctx, "question": q}).content
        st.write(ans)

        sources = [(h.metadata.get("page", 0) + 1, h.page_content) for h in hits]
        with st.expander("📚 Sources"):
            for i, (page, text) in enumerate(sources, 1):
                st.markdown(f"**Chunk {i}**, page {page}")
                st.write(text)

    st.session_state.history.append({"role": "assistant", "text": ans, "sources": sources})