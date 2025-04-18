import os
import json
import logging
from datetime import datetime
import streamlit as st
from dotenv import load_dotenv

import sentiment_agent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="Customer Service Bot",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Lazy imports with error handling
def import_agents():
    try:
        from sentiment_agent import SentimentAgent
        from knowledge_agent import KnowledgeAgent
        from llm_agent import LLMAgent
        from session_manager import SessionManager
        from data_sanitizer import DataSanitizer
        from visualization.emotion_charts import EmotionVisualizer
        return (SentimentAgent, KnowledgeAgent, LLMAgent, 
                SessionManager, DataSanitizer, EmotionVisualizer)
    except ImportError as e:
        st.error(f"Module import error: {str(e)}")
        st.stop()

(SentimentAgent, KnowledgeAgent, LLMAgent, 
 SessionManager, DataSanitizer, EmotionVisualizer) = import_agents()

# Initialize session state
if 'session_manager' not in st.session_state:
    st.session_state.session_manager = SessionManager()
if 'debug_data' not in st.session_state:  # Add this line
    st.session_state.debug_data = {}      # Initialize empty debug data
if 'knowledge_agent' not in st.session_state:
    st.session_state.knowledge_agent = None
if 'sentiment_agent' not in st.session_state:
    st.session_state.sentiment_agent = None
if 'llm_agent' not in st.session_state:
    st.session_state.llm_agent = None
if 'data_sanitizer' not in st.session_state:
    st.session_state.data_sanitizer = DataSanitizer()

# Initialize agents with caching
@st.cache_resource
def initialize_agents():
    try:
        session_manager = SessionManager()
        visualizer = EmotionVisualizer(session_manager)
        
        return (
            KnowledgeAgent(),
            SentimentAgent(),
            LLMAgent(model_name="gpt-4-turbo-preview"),
            session_manager,
            visualizer
        )
    except Exception as e:
        logger.error(f"Initialization error: {str(e)}")
        st.error("System initialization failed. Please check logs.")
        st.stop()

if st.session_state.knowledge_agent is None:
    with st.spinner("🚀 Loading AI components..."):
        try:
            (st.session_state.knowledge_agent,
             st.session_state.sentiment_agent,
             st.session_state.llm_agent,
             session_manager,
             st.session_state.visualizer) = initialize_agents()
            st.session_state.session_manager = session_manager
        except Exception as e:
            st.error(f"Initialization failed: {str(e)}")
            st.stop()

def display_rating_buttons(message_index: int):
    """Integrated rating system"""
    current_message = st.session_state.session_manager.current_session['history'][message_index]
    
    st.markdown("---")
    cols = st.columns([2, 3])
    with cols[0]:
        if not current_message.get('resolved'):
            if st.button(
                "✅ Mark Resolved",
                key=f"resolve_{message_index}",
                help="Confirm this response solved your issue",
                type="primary"
            ):
                st.session_state.session_manager.mark_message_resolved(message_index)
    with cols[1]:
        if current_message.get('resolved'):
            if current_message.get('rating'):
                st.success(f"Rated: {'⭐' * current_message['rating']}")
            else:
                st.write("**Rate the solution quality:**")
                rating_cols = st.columns(5)
                for i in range(1, 6):
                    with rating_cols[i-1]:
                        if st.button(
                            f"{i}⭐",
                            key=f"rate_{message_index}_{i}",
                            on_click=lambda i=i: st.session_state.session_manager.mark_message_resolved(
                                message_index, rating=i
                            )
                        ):
                            st.experimental_rerun()

def process_user_input(user_query: str):
    """Process user query through enhanced AI pipeline"""
    try:
        # Sanitize and analyze input
        sanitized_query = st.session_state.data_sanitizer.sanitize_text(user_query)
        # After sentiment analysis
        analysis = st.session_state.sentiment_agent.analyze(sanitized_query)
        tone_guidance = st.session_state.sentiment_agent.generate_tone_guidance(analysis)

        # Convert tone guidance to instruction string
        tone_instruction = f"""
        Respond with:
        - Base tone: {tone_guidance['base_tone']}
        - Strategy: {tone_guidance['emotional_strategy'].get('structure', 'general')}
        - Empathy level: {tone_guidance['emotional_strategy'].get('empathy', 2)}/5
        - Urgency: {tone_guidance['urgency_level']}
        """

        # Add to emotion timeline
        timeline_entry = {
            "timestamp": datetime.now().isoformat(),
            "sentiment_score": analysis['sentiment']['score'],  # Correct
            "valence": analysis['valence'],  # New field
            "dominant_emotion": analysis['emotions'][0]['label'] if analysis['emotions'] else 'neutral',
            "intensity_trend": analysis['intensity_trend']  # New field
        }

        st.session_state.debug_data = {
            'last_analysis': analysis,
            'timeline_entry': timeline_entry,
            'current_timeline': st.session_state.session_manager.current_session['emotion_timeline']
        }

        # Store in session
        st.session_state.session_manager.current_session['emotion_timeline'].append(timeline_entry)
        
        # Store user message with analytics
        st.session_state.session_manager.add_message_to_current_session(
            role="user",
            content=sanitized_query,
            sentiment_score=analysis['sentiment']['score'],
            emotions=analysis['emotions']
        )
        
        # Retrieve knowledge context
        context = {"text": "", "sources": []}
        response_container = st.empty()  # Create empty container first
        
        if st.session_state.knowledge_agent:
            with st.spinner("🔍 Searching knowledge base..."):
                try:
                    context = st.session_state.knowledge_agent.get_context(sanitized_query)
                    # Display results outside of status container
                    # In the knowledge retrieval section (replace the existing context display code):
                    if context.get("sources"):
                        with response_container.container():
                            with st.status("🔍 Analyzing knowledge base...", expanded=True) as status:
                                st.markdown("### Relevant Information Found")
                                
                                for idx, source in enumerate(context["sources"][:3]):
                                    cols = st.columns([1, 10])
                                    with cols[0]:
                                        st.success("✅")  # Checkmark indicator
                                    with cols[1]:
                                        st.markdown(f"""
                                        **Match {idx+1}**  
                                        **Relevance:** `{source.get('score', 0.0):.2f}`  
                                        **Excerpt:**  
                                        ```{source.get('content', 'No content available')[:200]}...```
                                        """)
                                    st.markdown("---")
                                
                                status.update(label=f"✅ Found {len(context['sources'])} relevant items", 
                                            state="complete")

                    else:
                        with st.status("🔍 Knowledge Search", expanded=True) as status:
                            st.warning("No relevant documents found")
                            status.update(label="⚠️ No matches found", state="error")

                except Exception as e:
                    logger.error(f"Knowledge retrieval error: {str(e)}")
                    context["text"] = f"Error: {str(e)}"

        # Handle verification flow separately
        if context.get("requires_verification"):
            with st.chat_message("assistant"):
                st.markdown("Please verify your order details:")
                
            with st.form(key="order_verification"):
                order_number = st.text_input("Order Number")
                email = st.text_input("Email Address")
                
                if st.form_submit_button("Verify"):
                    # Process verification with raw (unsanitized) input
                    order_details = st.session_state.knowledge_agent.get_order_details(
                        order_number, 
                        email
                    )
                    if order_details:
                        st.session_state.session_manager.add_message_to_current_session(
                            role="assistant",
                            content=f"Order Status: {order_details['status']}"
                        )
                    else:
                        st.error("Verification failed")
            return  # Exit early for verification flow
        
        # Generate tone instruction
        try:
            tone_guidance = st.session_state.sentiment_agent.generate_tone_guidance(analysis)
        except KeyError as e:
            logger.error(f"Tone guidance error: {str(e)}")
            tone_instruction = f"""
            Respond using:
            - Base tone: {tone_guidance['base_tone']}
            - Strategy: {tone_guidance['emotional_strategy']['structure']}
            - Empathy: {tone_guidance['emotional_strategy']['empathy']}/5
            - Urgency: {tone_guidance['urgency_level']}
            """
        
        # Display sentiment analysis
        with st.status("💭 Analyzing emotions...", expanded=True) as status:
            try:
                cols = st.columns(2)
                with cols[0]:
                    st.markdown("### Customer Sentiment")
                    sentiment = analysis["sentiment"]
                    st.metric(
                        label="Dominant Mood",
                        value=sentiment["label"].upper(),
                        delta=f"Confidence: {sentiment['score']:.2%}"
                    )
                with cols[1]:
                    st.markdown("### Emotional Breakdown")
                    if analysis["emotions"]:
                        for emotion in analysis["emotions"][:3]:  # Show top 3 emotions
                            st.markdown(
                                f"**{emotion['label'].title()}**  \n"
                                f"`{emotion['score']:.2%}` confidence"
                            )
                            st.progress(
                                emotion["score"],
                                text=f"Intensity Level: {emotion['score']:.0%}"
                            )
                    else:
                        st.warning("No strong emotions detected")
                status.update(label="✅ Emotional analysis completed", state="complete")
            except Exception as e:
                logger.error(f"Sentiment display error: {str(e)}")
                st.error("Failed to display emotion analysis")


        # Generate and display response
        response_content = ""
        if st.session_state.llm_agent:
            response_container = st.empty()
            displayed_response = ""
            
            try:
                # Update the response generation call:
                for chunk in st.session_state.llm_agent.generate_response_stream(
                    query=sanitized_query,
                    context={
                        "text": context['text'],
                        "sentiment_analysis": {
                            'label': analysis['sentiment']['label'],
                            'intensity': analysis['sentiment']['score'],
                            'valence': analysis['valence']
                        }
                    },
                    history=st.session_state.session_manager.current_session['history'],
                    tone_instruction=tone_instruction
                ):
                    displayed_response += chunk
                    response_container.markdown(displayed_response + "▌")
                    
                response_container.markdown(displayed_response)
                
                # Store assistant response
                st.session_state.session_manager.add_message_to_current_session(
                    role="assistant",
                    content=displayed_response
                )
                
                # Add resolution controls
                message_index = len(st.session_state.session_manager.current_session['history']) - 1
                st.markdown("---")
                cols = st.columns([1, 4])
                with cols[0]:
                    if st.button("✅ Mark Resolved", 
                            key=f"resolve_{message_index}",
                            help="Mark this response as finalized"):
                        st.session_state.session_manager.mark_message_resolved(message_index)
                        st.rerun()
                with cols[1]:
                    if st.session_state.session_manager.current_session['history'][message_index].get('resolved'):
                        display_rating_buttons(message_index)
                    else:
                        st.caption("Rate resolution after marking resolved")
                        
            except Exception as e:
                response_content = f"⚠️ Error: {str(e)}"
                logger.error(f"Response generation failed: {str(e)}")

        return response_content
    
    except Exception as e:
        logger.error(f"Processing error: {str(e)}")
        return f"System error: {str(e)}"

# Sidebar components
with st.sidebar:
    st.markdown("""
    <div style='text-align: center;'>
        <h2>📊 Analytics Dashboard</h2>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    if st.checkbox("Show debug data"):
        if st.session_state.debug_data:  # Check if data exists
            st.write("### Debug Information")
            st.write(st.session_state.debug_data)
        else:
            st.write("No debug data available yet - chat to generate!")
    if st.checkbox("📈 Show Emotion Analytics"):
        st.session_state.visualizer.display_analytics_dashboard()
    
    st.markdown("---")
    st.write("### Session Management")
    
    # Get fresh session list every render
    current_sessions = st.session_state.session_manager.get_all_session_titles()
    
    selected_session = st.selectbox(
        "Active Sessions",
        ["New Session"] + current_sessions,
        key="session_selector"
    )
    
    if selected_session == "New Session":
        new_name = st.text_input("Session Name:", "Untitled Conversation")
        if st.button("Create New Session"):
            st.session_state.session_manager.create_session(new_name)
            st.rerun()  # Force refresh after creation
    else:
        # Switch to existing session logic
        if st.button("Switch to Selected Session"):
            selected_session_obj = st.session_state.session_manager.get_session_by_title(selected_session)
            st.session_state.session_manager.current_session = selected_session_obj
            st.rerun()
    
    st.markdown("---")
    if st.button("🧹 Clear Current Session"):
        st.session_state.session_manager.clear_current_session()
        st.rerun()
    
    st.download_button(
        "📥 Export Conversation",
        data=json.dumps(st.session_state.session_manager.current_session, indent=2),
        file_name="conversation.json",
        mime="application/json"
    )

# Main interface
st.title("🤖 AI Customer Support Assistant")
st.caption("Enhanced with Emotional Intelligence and Context Awareness")

# Display chat history
for idx, message in enumerate(st.session_state.session_manager.current_session.get('history', [])):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        st.caption(f"{datetime.fromisoformat(message['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Show resolution controls immediately below message
        if message["role"] == "assistant":
            display_rating_buttons(idx)

# Input handling
if prompt := st.chat_input("How can I help you today?"):
    with st.chat_message("user"):
        st.markdown(prompt)
    
    with st.chat_message("assistant"):
        response = process_user_input(prompt)
        if response:
            st.markdown(response)

# Deployment configuration
if not os.path.exists("requirements.txt"):
    with open("requirements.txt", "w") as f:
        f.write("""
streamlit==1.30.0
openai==1.14.0
langchain==0.1.9
langchain-openai==0.0.8
langchain-community==0.0.25
faiss-cpu==1.7.4
python-dotenv==1.0.0
transformers==4.35.2
torch==2.1.0
numpy==1.26.2
sympy==1.12.0
plotly==5.18.0
pandas==2.1.4
presidio-analyzer==2.2.33
presidio-anonymizer==2.2.33
reportlab==4.0.4
sentence-transformers==2.2.2
spacy==3.7.0
typing-extensions==4.12.0
huggingface_hub==0.16.4
httpx==0.27.2
""")

if not os.path.exists("vercel.json"):
    with open("vercel.json", "w") as f:
        json.dump({
            "builds": [{"src": "app.py", "use": "@vercel/python"}],
            "routes": [{"src": "/(.*)", "dest": "app.py"}]
        }, f, indent=2)

        