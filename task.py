import os
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

load_dotenv()
api_key = os.getenv("AI21_API_KEY")
client = AI21Client(api_key=api_key)

mongo_client = MongoClient("mongodb://localhost:27017")
db = mongo_client["chat_history_db"]
chat_collection = db["btech_conversations"]
session_collection = db["chat_sessions"]
doc_collection = db["documents"]
fs = gridfs.GridFS(db)

# Start or select session
session_choice = input("Start a new session? (y/n): ").strip().lower()
if session_choice == "y":
    # Create new session
    session_id = str(uuid.uuid4())
    session_description = input("Enter a short description for this session: ").strip()

    # Ask for mode only for new sessions
    mode = input("\nChoose answer source - (1) Local documents or (2) Global knowledge? Enter 1 or 2: ").strip()
    if mode not in ["1", "2"]:
        print("Invalid choice. Exiting.")
        exit()
    mode_name = "Local" if mode == "1" else "Global"

    session_collection.insert_one({
        "_id": session_id,
        "description": session_description,
        "created_at": datetime.now(),
        "mode": mode
    })
    print(f"New session created with ID: {session_id}")

    # Ask to upload documents (only for new sessions)
    upload_docs = input("\nDo you want to upload documents? (y/n): ").strip().lower()
    if upload_docs == "y":
        def store_file_in_gridfs(filepath, filetype):
            filename = os.path.basename(filepath)
            if fs.find_one({"filename": filename}):
                print(f"File already exists in GridFS: {filename} – Skipping.")
                return
            try:
                with open(filepath, "rb") as f:
                    fs.put(f, filename=filename, filetype=filetype, uploaded_at=datetime.now())
                    print(f"Saved {filename} to GridFS.")
            except Exception as e:
                print(f"Error saving {filename} to GridFS: {e}")

        def store_document_in_db(filename, filetype, content):
            if not content.strip():
                print(f"File is empty: {filename}")
                return
            existing = doc_collection.find_one({"filename": filename, "filetype": filetype})
            if existing:
                print(f"Document already exists in DB: {filename} ({filetype}) – Skipping.")
                return
            doc_collection.insert_one({
                "session_id": session_id,
                "filename": filename,
                "filetype": filetype,
                "content": content,
                "uploaded_at": datetime.now()
            })
            print(f"Stored in DB: {filename} ({filetype})")

        def extract_text_from_pdf(pdf_path):
            try:
                doc = fitz.open(pdf_path)
                return "\n".join([page.get_text() for page in doc])
            except Exception as e:
                print(f"Error reading PDF {pdf_path}: {e}")
                return ""

        def read_excel_to_text(path):
            try:
                df = pd.read_excel(path, engine="openpyxl")
                return df.to_string(index=False)
            except Exception as e:
                print(f"Error reading Excel file {path}: {e}")
                return ""

        def extract_text_from_docx(docx_path):
            try:
                doc = Document(docx_path)
                return "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
            except Exception as e:
                print(f"Error reading DOCX file {docx_path}: {e}")
                return ""

        # Upload files
        if os.path.exists("doc.txt"):
            store_file_in_gridfs("doc.txt", "text")
            with open("doc.txt", "r", encoding="utf-8") as file:
                doc_text = file.read()
                store_document_in_db("doc.txt", "text", doc_text)
        else:
            print("doc.txt file not found.")

        if os.path.exists("Full.pdf"):
            store_file_in_gridfs("Full.pdf", "pdf")
            pdf_text = extract_text_from_pdf("Full.pdf")
            store_document_in_db("Full.pdf", "pdf", pdf_text)
        else:
            print("Full.pdf file not found.")

        if os.path.exists("sample.xlsx"):
            store_file_in_gridfs("sample.xlsx", "excel")
            excel_text = read_excel_to_text("sample.xlsx")
            store_document_in_db("sample.xlsx", "excel", excel_text)
        else:
            print("sample.xlsx file not found.")

        if os.path.exists("title.docx"):
            store_file_in_gridfs("title.docx", "docx")
            docx_text = extract_text_from_docx("title.docx")
            store_document_in_db("title.docx", "docx", docx_text)
        else:
            print("title.docx file not found.")
    else:
        print("Skipping document upload.")

else:
    # Existing session
    print("\nExisting sessions:")
    existing_sessions = list(session_collection.find())
    if not existing_sessions:
        print("No existing sessions found. Please create a new one.")
        exit()

    for s in existing_sessions:
        created_at_str = s["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        mode_str = "Local" if s.get("mode") == "1" else "Global"
        print(f"ID: {s['_id']} | {s['description']} | Created: {created_at_str} | Mode: {mode_str}")

    session_id = input("\nEnter existing session ID: ").strip()
    existing = session_collection.find_one({"_id": session_id})
    if not existing:
        print("Session ID not found. Exiting.")
        exit()

    # Load mode from DB and skip document upload
    mode = existing.get("mode", "2")  # Default to Global
    mode_name = "Local" if mode == "1" else "Global"
    print(f"Continuing in {mode_name} mode. Skipping document upload.")

# Prepare local document content if needed
doc_content = ""
docs_found = False
for doc in doc_collection.find({"session_id": session_id}):  # ← filter by session
    docs_found = True
    doc_content += f"[From {doc['filename']} ({doc['filetype']})]\n{doc['content']}\n\n"

if not docs_found and mode == "1":
    print("No documents found in the database. Local mode will not work.")

# Show previous chat history
print("\n📜 Previous chat history:")
for record in chat_collection.find({"session_id": session_id}).sort("timestamp"):
    print(f"\n👤 User: {record['question']}")
    print(f"🤖 Bot: {record['answer']}")

from datetime import datetime
from ai21 import AI21Client
from ai21.models.chat import ChatMessage

while True:
    user_input = input(f"\nAsk a question (or type 'exit' to end from {mode_name}): ").strip()
    
    if user_input.lower() == "exit":
        switch = input("\nDo you want to switch mode instead of exiting? (y/n): ").strip().lower()
        if switch == "y":
            new_mode = input("Choose new mode - (1) Local documents or (2) Global knowledge? Enter 1 or 2: ").strip()
            if new_mode in ["1", "2"]:
                mode = new_mode
                mode_name = "Local" if mode == "1" else "Global"
                session_collection.update_one({"_id": session_id}, {"$set": {"mode": mode}})
                print("Mode switched successfully.")
            else:
                print("Invalid choice. Staying in current mode.")
            continue
        else:
            print("Session ended. Goodbye!")
            break

    if mode == "1":  
        system_message = (
            "You are an assistant that must only answer using the following document. "
            "Do not use any external knowledge.\n\n"
            f"{doc_content}\n\n"
            "Instructions:\n"
            "- If the answer is found, respond with '(From local source)' followed by the answer.\n"
            "- If the answer is not found in the document, respond with exactly: 'Not available in the document.'\n"
            "- Do not guess or add any extra information beyond the document.\n"
            "- Format the answer in bullet points if possible."
        )
    else:  
        system_message = (
            "You are an AI assistant that answers questions using general world knowledge. "
            "Important: start your answer with '(From Global source)'.\n"
            "Then, answer using concise bullet points only. Avoid long paragraphs or headings."
        )

    # Prepare chat messages
    messages = [
        ChatMessage(role="system", content=system_message),
        ChatMessage(role="user", content=user_input),
    ]

    try:
        # Call AI21 chat completion API
        chat_completions = client.chat.completions.create(
            model="jamba-large-1.7",
            messages=messages,
            temperature=0.2,   
            maxTokens=500     
        )

        # Extract the assistant's answer
        answer = chat_completions.choices[0].message.content
        print("\nAnswer:\n", answer)

        # Save chat to MongoDB
        chat_record = {
            "session_id": session_id,
            "mode": "local" if mode == "1" else "global",
            "question": user_input,
            "answer": answer,
            "timestamp": datetime.now()
        }
        chat_collection.insert_one(chat_record)
        print("Chat saved successfully.")

    except Exception as e:
        print("Error during AI response:", str(e))
