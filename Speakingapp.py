import streamlit as st
import google.generativeai as genai
from groq import Groq
from streamlit_mic_recorder import mic_recorder
from gtts import gTTS
from io import BytesIO
import base64

# --- 1. CẤU HÌNH API ---
try:
    if "GOOGLE_API_KEY" in st.secrets:
        GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
        GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
    else:
        # Fallback cho máy local
        GOOGLE_API_KEY = "AIza..." 
        GROQ_API_KEY = "gsk_..."
except:
    st.stop()

genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')
groq_client = Groq(api_key=GROQ_API_KEY)

# --- 2. KHỞI TẠO SESSION STATE ---
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "mic_key" not in st.session_state:
    st.session_state.mic_key = 0
if "last_audio_memory" not in st.session_state:
    st.session_state.last_audio_memory = None

# --- 3. HÀM HỖ TRỢ ---

def text_to_speech(text):
    """Chuyển văn bản thành giọng nói"""
    try:
        tts = gTTS(text=text, lang='en', tld='co.uk')
        audio_bytes = BytesIO()
        tts.write_to_fp(audio_bytes)
        audio_bytes.seek(0)
        audio_base64 = base64.b64encode(audio_bytes.read()).decode()
        # Autoplay audio
        audio_html = f'<audio autoplay="true" style="display:none;"><source src="data:audio/mp3;base64,{audio_base64}" type="audio/mp3"></audio>'
        st.markdown(audio_html, unsafe_allow_html=True)
    except: pass

def whisper_stt(audio_bytes):
    try:
        return groq_client.audio.transcriptions.create(
            file=("input.wav", audio_bytes), 
            model="whisper-large-v3", 
            response_format="text", 
            language="en")
    except Exception as e:
        st.error(f"Lỗi Groq: {e}")
        return None

def repair_transcription(raw_text):
    """Sửa lỗi nghe nhầm và gắn cờ báo lỗi phát âm"""
    try:
        repair_prompt = f"""
        Act as a Speech-to-Text Analysis Tool.
        Raw Input: "{raw_text}"
        Task:
        1. Identify phonetic/transcription errors (e.g., "bitch" vs "beach").
        2. IF ERROR: Correct it AND append "[PRONUNCIATION ERROR: <wrong> -> <right>]".
        3. IF NO ERROR: Output original text.
        4. CRITICAL: DO NOT fix grammar. Only fix "Misheard" words.
        """
        response = model.generate_content(repair_prompt)
        return response.text.strip()
    except:
        return raw_text

def process_final_answer(user_content):
    if user_content:
        # 1. Sửa lỗi & Gắn cờ
        with st.spinner("Đang phân tích âm thanh..."):
            analyzed_text = repair_transcription(user_content)
        
        # 2. Xử lý hiển thị (Ẩn tag lỗi với người dùng cho đẹp)
        if "[PRONUNCIATION ERROR" in analyzed_text:
            display_text = analyzed_text.split("[PRONUNCIATION ERROR")[0].strip()
            error_detail = analyzed_text.split("[PRONUNCIATION ERROR")[1].replace("]", "")
            st.toast(f"⚠️ Phát hiện lỗi phát âm{error_detail}", icon="🗣️")
        else:
            display_text = analyzed_text

        st.session_state.chat_history.append({"role": "user", "content": display_text})
        
        # 3. Gửi cho Giám khảo chấm
        with st.spinner("Giám khảo đang chấm điểm..."):
            try:
                full_prompt = system_instruction + f"\nUser Answer: {analyzed_text}"
                response = model.generate_content(full_prompt)
                full_reply = response.text
                
                voice_content = full_reply 
                
                if "|||" in full_reply:
                    parts = full_reply.split("|||")
                    feedback_part = parts[0].strip()
                    question_part = parts[1].strip() if len(parts) > 1 else ""
                    
                    st.session_state.chat_history.append({"role": "feedback_box", "content": feedback_part})
                    
                    if question_part:
                        st.session_state.chat_history.append({"role": "assistant", "content": question_part})
                        voice_content = question_part
                else:
                    st.session_state.chat_history.append({"role": "assistant", "content": full_reply})

                st.session_state.audio_to_play = voice_content
                
            except Exception as e:
                st.error(f"Lỗi AI: {e}")

# --- 4. SYSTEM PROMPT ---
system_instruction = """
You are a professional IELTS Speaking Examiner.
INPUT DATA: User input may contain "[PRONUNCIATION ERROR: X -> Y]".
- This means user said X but meant Y. Penalize Pronunciation score if seen.
- Proceed conversation with meaning of Y.

MANDATORY RESPONSE FORMAT:
**Band: [Score]** 📝 [Correction/Feedback] ||| [Natural Question]

RULES:
1. Use "|||" to separate Feedback (Text) and Next Question (Voice).
2. Be polite and encouraging in the voice part.
3. Be strict in the grading part.
"""

# --- 5. GIAO DIỆN ---
st.set_page_config(page_title="IELTS Ultimate", page_icon="🎓")
st.title("🎓 IELTS Speaking Pro")

# --- KHỞI TẠO CÂU CHÀO (FIX LỖI MÀN HÌNH TRẮNG) ---
# Kiểm tra nếu lịch sử rỗng -> Tạo câu hỏi đầu tiên ngay
if len(st.session_state.chat_history) == 0:
    try:
        # Prompt riêng để bắt đầu cuộc thi
        start_prompt = system_instruction + "\n\nTASK: Start the exam now with a polite greeting and the first Part 1 question."
        init = model.generate_content(start_prompt)
        init_text = init.text
        
        # Xử lý format cho câu đầu
        clean_text = init_text.replace("|||", "").strip() # Câu đầu thường không có điểm
        if "Band:" in clean_text: # Nếu lỡ có điểm thì tách ra
             clean_text = clean_text.split("|||")[-1].strip()
             
        st.session_state.chat_history.append({"role": "assistant", "content": clean_text})
        st.session_state.audio_to_play = clean_text
    except Exception as e:
        st.error("Lỗi khởi tạo: " + str(e))

# --- HIỂN THỊ CHAT ---
for msg in st.session_state.chat_history:
    role = msg["role"]
    content = msg["content"]
    
    if role == "user":
        with st.chat_message("user"):
            st.write(content)
    elif role == "feedback_box":
        st.warning(content, icon="⭐")
    elif role == "assistant":
        with st.chat_message("assistant"):
            st.write(content)

if "audio_to_play" in st.session_state and st.session_state.audio_to_play:
    text_to_speech(st.session_state.audio_to_play)
    st.session_state.audio_to_play = None

st.write("---")

# --- 6. INPUT AREA ---
tab_voice, tab_text = st.tabs(["🎙️ Ghi âm", "⌨️ Nhập phím"])

with tab_voice:
    audio_data = mic_recorder(
        start_prompt="Start", stop_prompt="Stop", 
        key=str(st.session_state.mic_key), format="wav"
    )
    
    if audio_data and "bytes" in audio_data:
        st.session_state.last_audio_memory = audio_data["bytes"]
        raw_text = whisper_stt(audio_data["bytes"])
        if raw_text:
            process_final_answer(raw_text)
