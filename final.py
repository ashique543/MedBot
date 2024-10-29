from flask import Flask, request, jsonify, render_template
from langchain.chains import ConversationChain
from langchain.chains.conversation.memory import ConversationBufferWindowMemory
from langchain.prompts import (
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
    ChatPromptTemplate,
    MessagesPlaceholder
)
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone
import google.generativeai as genai  # Import Gemini
from flask_cors import CORS

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Configure Gemini model
genai.configure(api_key="AIzaSyAqPZGrv4ZELWiEt0spuY-od33-GMSk7DY")  # Set your Gemini API key
gemini_model = genai.GenerativeModel("gemini-1.5-flash")

# Initialize Pinecone
pc = Pinecone(api_key='6fff7d16-e9f7-4344-b20c-02c3811047db')
index = pc.Index('alzehimers')

# Initialize SentenceTransformer model
model = SentenceTransformer('all-MiniLM-L6-v2')

# Custom Gemini-based language model
class GeminiLangChainModel:
    def __init__(self, model):
        self.model = model

    def predict(self, input):
        try:
            response = self.model.generate_content(input)
            return response.text
        except Exception as e:
            print(f"Error in GeminiLangChainModel: {e}")
            return "An error occurred while generating the response."

# Initialize LangChain components with custom Gemini model
gemini_llm = GeminiLangChainModel(model=gemini_model)
buffer_memory = ConversationBufferWindowMemory(k=3, return_messages=True)

system_msg_template = SystemMessagePromptTemplate.from_template(
    template="""Answer the question as truthfully as possible using the provided context, 
    and if the answer is not contained within the text below, say 'I DON'T KNOW, because it is irrelevant to our context'"""
)
human_msg_template = HumanMessagePromptTemplate.from_template(template="{input}")
prompt_template = ChatPromptTemplate.from_messages([system_msg_template, MessagesPlaceholder(variable_name="history"), human_msg_template])
conversation = ConversationChain(memory=buffer_memory, prompt=prompt_template, llm=gemini_llm, verbose=True)

# Session state simulation
session_state = {
    'responses': ["Hello, Welcome to our chatBot?"],
    'requests': []
}

# Helper functions
def find_match(input):
    try:
        input_em = model.encode(input).tolist()
        result = index.query(vector=input_em, top_k=2, includeMetadata=True)
        if 'matches' in result and len(result['matches']) >= 2:
            return result['matches'][0]['metadata']['text'] + "\n" + result['matches'][1]['metadata']['text']
        else:
            return "No sufficient matches found in the index."
    except Exception as e:
        print(f"Error in find_match: {e}")
        return "An error occurred while querying the index."

def query_refiner(conversation, query):
    # Use Gemini model to refine the query
    try:
        response = gemini_model.generate_content(
            f"Given the user query and previous conversation provided below, generate a refined question that can be used to retrieve relevant information from a knowledge base. Ensure the question is grammatically correct and includes proper spelling.\n\nUser Query: {query} and previous-questions:{conversation}\n\nRefined Question:\nExample 1:If the user query is 'Symptoms of Allergen', a refined question could be 'What are the common symptoms of the Allergen?'\n\nRefined Question:"
        )
        refined_query = response.text.strip()
        return refined_query
    except Exception as e:
        print(f"Error in query_refiner: {e}")
        return "An error occurred while refining the query."

def get_conversation_string(responses, requests):
    conversation_string = ""
    for i in range(len(responses) - 1):
        conversation_string += "Human: " + requests[i] + "\n"
        conversation_string += "Bot: " + responses[i + 1] + "\n"
    return conversation_string

def generate_alternative_questions(query):
    # Use Gemini model to generate alternative questions
    try:
        response = gemini_model.generate_content(
            f"Provide only 3 alternative questions related to '{query}' and give the alternative questions in simple English and they should sound good. You need not give any numbering of the questions."
        )
        alternatives = response.text.strip().split('\n')
        return [alt.strip() for alt in alternatives if alt.strip()]
    except Exception as e:
        print(f"Error in generate_alternative_questions: {e}")
        return ["An error occurred while generating alternative questions."]

@app.route('/')
def hello():
    return render_template('new.html')

@app.route('/send_message', methods=['POST'])
def send_message():
    data = request.json 
    user_message = data.get('message')
    print("User Message:", user_message)

    session_state['requests'].append(user_message)
    conversation_string = get_conversation_string(session_state['responses'], session_state['requests'])
    print("Conversation String:", conversation_string)

    refined_query = query_refiner(conversation_string, user_message)
    print("Refined Query:", refined_query)

    context = find_match(refined_query)
    print("Context:", context)

    response = conversation.predict(input=f"Context:\n{context}\n\nQuery:\n{user_message}")
    print("Response:", response)
    alternatives = generate_alternative_questions(refined_query)
    session_state['responses'].append(response)

    return jsonify({
        "response": response,
        "refined_query": refined_query,
        "related_questions": alternatives
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
