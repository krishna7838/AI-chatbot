import os
import requests
import uuid
import pandas as pd
from dotenv import load_dotenv
from ai21 import AI21Client
from ai21.models.chat import ChatMessage
from pymongo import MongoClient
from datetime import datetime
import fitz
from docx import Document
import gridfs
from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename

# Load environment variables
load_dotenv(override=True)
api_key = os.getenv("AI21_API_KEY")



# Initialize AI21 client
client = AI21Client(api_key=api_key)

# MongoDB setup
mongo_client = MongoClient("mongodb://localhost:27017")
db = mongo_client["chat_history_db"]
chat_collection = db["btech_conversations"]
session_collection = db["chat_sessions"]
doc_collection = db["documents"]
fs = gridfs.GridFS(db)

# Flask app
app = Flask(__name__)

def extract_text_from_pdf(pdf_file):
    doc = fitz.open(pdf_file)
    return "\n".join([page.get_text() for page in doc])

def read_excel_to_text(file):
    df = pd.read_excel(file, engine="openpyxl")
    return df.to_string(index=False)

def extract_text_from_docx(docx_file):
    doc = Document(docx_file)
    return "\n".join([para.text for para in doc.paragraphs if para.text.strip()])

def prepare_local_docs(session_id):
    doc_content = ""
    for doc in doc_collection.find({"session_id": session_id}):
        doc_content += f"[From {doc['filename']} ({doc['filetype']})]\n{doc['content']}\n\n"
    return doc_content


# List all sessions
@app.route("/sessions", methods=["GET"])
def list_sessions():
    sessions = session_collection.find({}, {"_id": 1, "description": 1, "mode": 1, "created_at": 1})
    result = []
    for s in sessions:
        result.append({
            "session_id": s["_id"],
            "description": s.get("description", ""),
            "mode": "Local" if s.get("mode") == "1" else "Global",
            "created_at": s.get("created_at").strftime("%Y-%m-%d %H:%M:%S")
        })
    return jsonify(result)

# Start a new session
@app.route("/start_session", methods=["POST"])
def start_session():
    data = request.json
    session_id = str(uuid.uuid4())
    description = data.get("description", "No description")
    mode = data.get("mode", "2")  # Default Global

    session_collection.insert_one({
        "_id": session_id,
        "description": description,
        "created_at": datetime.now(),
        "mode": mode
    })

    return jsonify({"session_id": session_id, "mode": "Local" if mode == "1" else "Global"})

@app.route("/history", methods=["POST"])
def get_history():
    data = request.json
    session_id = data.get("session_id")
    if not session_id:
        return jsonify({"error": "session_id is required"}), 400

    history = chat_collection.find({"session_id": session_id}).sort("timestamp", 1)
    result = []
    for h in history:
        timestamp = h.get("timestamp")
        result.append({
            "question": h.get("question", ""),
            "answer": h.get("answer", ""),
            "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S") if isinstance(timestamp, datetime) else "",
            "mode": h.get("mode", "unknown")
        })
    return jsonify(result)


# Chat route
@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    session_id = data.get("session_id")
    user_input = data.get("message", "")

    # Validate session
    session = session_collection.find_one({"_id": session_id})
    if not session:
        return jsonify({"error": "Invalid session_id"}), 400

    mode = str(session.get("mode", "2")).lower()

# Normalize to "1"/"2"
    if mode in ["1", "local"]:
        mode = "1"
        mode_name = "Local"
    else:
        mode = "2"
        mode_name = "Global"


    if mode == "1":
        docs = prepare_local_docs(session_id)
        #  Check if document content is empty
        if not docs.strip():
            return jsonify({
                "session_id": session_id,
                "user": user_input,
                "bot": "Document is empty."
            }), 200


        system_message = (
            
            "You are an assistant that must only answer using the following document. "
            "Do not use any external knowledge.\n\n"
            f"{docs}\n\n"
            "Formatting rules (must follow strictly):\n"
            "- Only use plain text.\n"
            "- Start your answer with '(From local source)'.\n"
            "- Each bullet must be on its own separate line, beginning with '- '.\n"
            "- Never combine two bullet points on the same line.\n"
            "- Never use bold, italics, or any markdown symbols (** or * or # or `).\n"
            "- Always respond in clear, concise bullet points, each starting with '- '.\n"
            "- Do not leave empty bullets.\n"
            "- Do not write paragraphs.\n"
            "- If the answer is not found in the document, reply exactly: 'Not available in the document.'\n"
            "- If the document is empty, respond with 'Document is empty.'"
        )
    else:
        system_message = (
            "You are an AI assistant that answers questions using general world knowledge.\n"
            "Formatting rules (must follow strictly):\n"
            "- Start your answer with '(From Global source)'.\n"
            "- Only use plain text.\n"
            "- Each bullet must be on its own separate line, beginning with '- '.\n"
            "- Never combine two bullet points on the same line.\n"
            "- Never use bold, italics, or any markdown symbols (** or * or # or `).\n"
            "- Respond using clear, concise bullet points starting each line with '- '.\n"
            "- Do not write paragraphs.\n"
            "- If you don't know the answer, say 'I don't have information on that.'"
        )

    messages = [
        ChatMessage(role="system", content=system_message),
        ChatMessage(role="user", content=user_input),
    ]

    try:
        response = client.chat.completions.create(
            model="jamba-large-1.7",
            messages=messages
        )
        choice = response.choices[0]
        answer = None
        if hasattr(choice, "message"):
            msg = choice.message
            if isinstance(msg, dict):
                answer = msg.get("content")
            else:
                answer = getattr(msg, "content", None) or str(msg)
        elif hasattr(choice, "content"):
            answer = choice.content
        elif isinstance(choice, dict) and "content" in choice:
            answer = choice["content"]

        if not answer or not str(answer).strip():
            answer = "No response from AI."

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Save chat in DB
    chat_collection.insert_one({
        "session_id": session_id,
        "mode": mode_name.lower(),
        "question": user_input,
        "answer": answer,
        "timestamp": datetime.now()
    })

    return jsonify({
        "session_id": session_id,
        "user": user_input,
        "bot": answer
    })

#switch mode route
from bson import ObjectId

@app.route("/switch_mode", methods=["POST"])
def switch_mode():
    data = request.json
    session_id = data.get("session_id")
    new_mode = data.get("mode")

    if new_mode not in ["1", "2"]:
        return jsonify({"error": "Invalid mode. Use 1 (Local) or 2 (Global)."}), 400

    # Try matching by ObjectId (old sessions)
    try:
        query_id = ObjectId(session_id)
        result = session_collection.update_one({"_id": query_id}, {"$set": {"mode": new_mode}})
    except Exception:
        result = None

    # If not found as ObjectId, try plain string (new sessions)
    if not result or result.matched_count == 0:
        result = session_collection.update_one({"_id": session_id}, {"$set": {"mode": new_mode}})

    if result.matched_count == 0:
        return jsonify({"error": "Session not found"}), 404

    return jsonify({
        "session_id": session_id,
        "new_mode": "Local" if new_mode == "1" else "Global"
    }), 200


# Upload documents
@app.route("/upload", methods=["POST"])
def upload_documents():
    session_id = request.form.get("session_id")
    files = request.files.getlist("files")
    if not session_id or not files:
        return jsonify({"error": "session_id and files are required"}), 400

    uploaded_files = []
    skipped_files = []

    for file in files:
        filename = secure_filename(file.filename)
        existing = fs.find_one({"filename": filename, "session_id": session_id})
        if existing:
            skipped_files.append(filename)
            continue

        filetype = filename.split(".")[-1].lower()

        # Save file in GridFS
        file.seek(0)
        file_id = fs.put(
            file,
            filename=filename,
            filetype=filetype,
            session_id=session_id,
            uploaded_at=datetime.now()
        )
        file.seek(0)

        content = ""
        try:
            if filetype == "pdf":
                pdf_bytes = file.read()
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                content = "\n".join([page.get_text() for page in doc])
            elif filetype in ["docx", "doc"]:
                content = extract_text_from_docx(file)
            elif filetype in ["xls", "xlsx"]:
                content = read_excel_to_text(file)
            elif filetype == "txt":
                content = file.read().decode("utf-8")
        except Exception as e:
            content = f"Error extracting text: {str(e)}"

        # Store text content in documents collection
        doc_collection.insert_one({
            "session_id": session_id,
            "filename": filename,
            "filetype": filetype,
            "content": content,
            "uploaded_at": datetime.now(),
            "gridfs_id": file_id
        })

        uploaded_files.append({"file_id": str(file_id), "filename": filename})

    return jsonify({
        "message": f"{len(uploaded_files)} files uploaded successfully",
        "files": uploaded_files,
        "skipped_files": skipped_files
    })

# List documents for a session
@app.route("/documents", methods=["POST"])
def list_documents():
    data = request.json
    session_id = data.get("session_id")
    if not session_id:
        return jsonify({"error": "session_id is required"}), 400

    try:
        # Fetch files from GridFS for this session
        files = fs.find({"session_id": session_id})

        result = []
        for f in files:
            result.append({
                "file_id": str(f._id),
                "filename": f.filename or "Unnamed File",
                "length": f.length,
                "upload_date": f.upload_date.strftime("%Y-%m-%d %H:%M:%S")
            })

        print(f"Documents for session {session_id}: {[f.filename for f in files]}")  # debug
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

#delete documents
@app.route("/delete_document/<file_id>", methods=["DELETE"])
def delete_document(file_id):
    try:
        # Convert to ObjectId
        obj_id = ObjectId(file_id)

        # Find file in GridFS
        file = fs.get(obj_id)
        filename = file.filename

        # Delete from GridFS
        fs.delete(obj_id)

        # Delete text content from documents collection
        doc_collection.delete_one({"gridfs_id": obj_id})

        return jsonify({"message": f"Document '{filename}' deleted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400
# Home route
@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")

# Delete session
@app.route("/delete_session/<session_id>", methods=["DELETE"])
def delete_session(session_id):
    chat_collection.delete_many({"session_id": session_id})
    doc_collection.delete_many({"session_id": session_id})
    for f in fs.find({"session_id": session_id}):
        fs.delete(f._id)
    session_collection.delete_one({"_id": session_id})  # keep as string
    return jsonify({"message": "Session deleted successfully"})

# Run app
if __name__ == "__main__":
    app.run(debug=True)