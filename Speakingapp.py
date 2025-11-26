import streamlit as st
import google.generativeai as genai
from audiorecorder import audiorecorder
import speech_recognition as sr
from gtts import gTTS
from io import BytesIO
import base64
from pydub import AudioSegment
import shutil
import os

# --- 1. CẤU HÌNH API KEY (AN TOÀN TUYỆT ĐỐI) ---
# Code này tự động lấy Key từ secrets.toml (Local) hoặc Secrets (Cloud)
# Tuyệt đối KHÔNG viết Key cứng vào đây nữa.
try:
    if "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
        genai.configure(api_key=api_key)
    else:
        st.error("🚨 Chưa tìm thấy API Key! Hãy tạo file .streamlit/secrets.toml")
        st.stop()
except Exception as e:
    st.error(f"Lỗi cấu hình Key: {e}")
    st.stop()

# Dùng bản 1.5 Flash để ổn định nhất trên Cloud (Bản 2.5 đôi khi chưa public rộng rãi)
model = genai.GenerativeModel('gemini-2.5-flash')

# --- 2. CẤU HÌNH FFMPEG ---
if shutil.which("ffmpeg"):
    AudioSegment.converter = shutil.which("ffmpeg")
else:
    # Fallback cho Windows Local
    AudioSegment.converter = "ffmpeg.exe" 
    AudioSegment.ffmpeg = "ffmpeg.exe"
    AudioSegment.ffprobe = "ffprobe.exe"

# --- 3. KHỞI TẠO STATE ---
if "recorder_key" not in st.session_state:
    st.session_state.recorder_key = "0"

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# --- 4. CÁC HÀM XỬ LÝ ---
def text_to_speech(text):
    """Chuyển văn bản thành giọng nói (Anh-Anh)"""
    try:
        tts = gTTS(text=text, lang='en', tld='co.uk') 
        audio_bytes = BytesIO()
        tts.write_to_fp(audio_bytes)
        audio_bytes.seek(0)
        audio_base64 = base64.b64encode(audio_bytes.read()).decode()
        audio_html = f"""
            <audio autoplay="true" style="display:none;">
            <source src="data:audio/mp3;base64,{audio_base64}" type="audio/mp3">
            </audio>
        """
        st.markdown(audio_html, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Lỗi TTS: {e}")

def speech_to_text(audio_segment):
    """Chuyển AudioSegment thành văn bản"""
    r = sr.Recognizer()
    try:
        wav_io = BytesIO()
        audio_segment.export(wav_io, format="wav") 
        wav_io.seek(0) 
        with sr.AudioFile(wav_io) as source:
            r.adjust_for_ambient_noise(source)
            audio_data = r.record(source)
            text = r.recognize_google(audio_data, language="en-US")
            return text
    except sr.UnknownValueError:
        return None
    except Exception as e:
        st.error(f"Lỗi STT: {e}")
        return None

# --- 5. KỊCH BẢN AI ---
system_instruction = """
You are a strict IELTS Speaking Examiner. 
Your GOAL: Test the user's speaking ability naturally.

RULES FOR RESPONSE FORMAT:
1. IF USER MAKES A MISTAKE:
   Output format: [Brief Correction] ||| [Next Question]
   Example: You said "I go". Correct: "I went". ||| What did you do there?

2. IF USER IS CORRECT:
   Output format: [Next Question]
   Example: Interesting. ||| Do you prefer working alone or in a team?

IMPORTANT:
- Use "|||" to separate feedback (text only) and speech (voice).
- The part AFTER "|||" will be spoken by voice. Keep it natural.
- Start with a Part 1 question about Work, Study, or Hobbies.
"""

# Khởi tạo Chat
if "chat" not in st.session_state:
    st.session_state.chat = model.start_chat(history=[])
    try:
        first_resp = st.session_state.chat.send_message(system_instruction)
        initial_text = first_resp.text
        if "|||" in initial_text:
            _, q = initial_text.split("|||")
            st.session_state.chat_history.append({"role": "assistant", "content": q.strip()})
            st.session_state.initial_audio = q.strip()
        else:
            st.session_state.chat_history.append({"role": "assistant", "content": initial_text})
            st.session_state.initial_audio = initial_text
    except Exception as e:
        st.error(f"Lỗi khởi tạo AI: {e}. Vui lòng kiểm tra API Key hoặc Model.")

# --- 6. GIAO DIỆN ---
st.set_page_config(page_title="IELTS Examiner", page_icon="🇬🇧")
st.title("🇬🇧 IELTS Speaking Virtual Examiner")
st.caption("Nghe câu hỏi -> Bấm ghi âm để trả lời -> Nhận sửa lỗi")

# Hiển thị lịch sử
for msg in st.session_state.chat_history:
    role = "🧑‍💻 Bạn" if msg["role"] == "user" else "👨‍🏫 Giám khảo"
    if role == "👨‍🏫 Giám khảo" and "[Feedback]" in msg["content"]:
         st.warning(msg["content"])
    else:
         with st.chat_message(msg["role"]):
            st.write(msg["content"])

# Phát âm thanh chào mừng
if "initial_audio" in st.session_state:
    text_to_speech(st.session_state.initial_audio)
    del st.session_state.initial_audio

st.write("---")

# NÚT GHI ÂM
audio = audiorecorder("Nhấn để trả lời", "Đang ghi âm...", key=st.session_state.recorder_key)

if len(audio) > 0:
    # 1. STT
    user_text = speech_to_text(audio)
    
    if user_text:
        st.session_state.chat_history.append({"role": "user", "content": user_text})
        
        # 2. Gửi cho AI
        with st.spinner("Giám khảo đang chấm điểm..."):
            try:
                response = st.session_state.chat.send_message(user_text)
                full_reply = response.text
                
                # 3. Tách phản hồi
                voice_content = full_reply
                if "|||" in full_reply:
                    feedback_part, question_part = full_reply.split("|||")
                    st.session_state.chat_history.append({"role": "assistant", "content": f"[Feedback] {feedback_part.strip()}"})
                    voice_content = question_part.strip()
                    st.session_state.chat_history.append({"role": "assistant", "content": voice_content})
                else:
                    st.session_state.chat_history.append({"role": "assistant", "content": full_reply})
                
                # 4. Đọc to
                text_to_speech(voice_content)
                
            except Exception as e:
                st.error(f"Lỗi AI trả lời: {e}")

        # 5. Reset nút
        st.session_state.recorder_key = str(int(st.session_state.recorder_key) + 1)
        st.rerun()
    else:
        st.error("Không nghe rõ. Vui lòng thử lại.")
