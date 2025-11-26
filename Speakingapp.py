import streamlit as st
import google.generativeai as genai
from audiorecorder import audiorecorder
import speech_recognition as sr
from gtts import gTTS
from io import BytesIO
import base64
from pydub import AudioSegment

# --- 1. CẤU HÌNH ---

# API Key của bạn
GOOGLE_API_KEY = "AIzaSyDVUwkQnX93ReVVfAmCwnnsQorZrh09aI0"
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

# CẤU HÌNH FFMPEG (Quan trọng để không bị lỗi WinError 2)
# Đảm bảo 3 file .exe nằm ngay cạnh file code này
AudioSegment.converter = "ffmpeg.exe"
AudioSegment.ffmpeg = "ffmpeg.exe"
AudioSegment.ffprobe = "ffprobe.exe"

# --- 2. KHỞI TẠO SESSION STATE ---
# Tạo bộ đếm để reset nút ghi âm sau mỗi lần nói
if "recorder_key" not in st.session_state:
    st.session_state.recorder_key = "0"

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# --- 3. HÀM XỬ LÝ ---

def text_to_speech(text):
    """Chuyển văn bản thành giọng nói (Anh-Anh) và tự động phát"""
    try:
        # tld='co.uk' -> Giọng Anh (British English)
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
    """Chuyển AudioSegment thành văn bản thông qua Google"""
    r = sr.Recognizer()
    try:
        # Chuyển sang WAV (RAM)
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

# --- 4. KỊCH BẢN AI (SYSTEM PROMPT) ---
# Logic tách luồng: Sửa lỗi ||| Câu hỏi mới
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

# Khởi tạo Chat Session
if "chat" not in st.session_state:
    st.session_state.chat = model.start_chat(history=[])
    # Gửi chỉ thị đầu tiên
    first_resp = st.session_state.chat.send_message(system_instruction)
    # Xử lý câu chào đầu tiên (thường AI sẽ đưa ra câu hỏi luôn)
    initial_text = first_resp.text
    if "|||" in initial_text:
        _, q = initial_text.split("|||")
        st.session_state.chat_history.append({"role": "assistant", "content": q.strip()})
        # Lưu vào biến tạm để lát nữa tự động đọc khi load trang
        st.session_state.initial_audio = q.strip()
    else:
        st.session_state.chat_history.append({"role": "assistant", "content": initial_text})
        st.session_state.initial_audio = initial_text

# --- 5. GIAO DIỆN ---
st.set_page_config(page_title="IELTS Examiner", page_icon="🇬🇧")
st.title("🇬🇧 IELTS Speaking Virtual Examiner")
st.caption("Nghe câu hỏi -> Bấm ghi âm để trả lời -> Nhận sửa lỗi")

# Hiển thị lịch sử
for msg in st.session_state.chat_history:
    role = "🧑‍💻 Bạn" if msg["role"] == "user" else "👨‍🏫 Giám khảo"
    # Nếu là feedback (bắt đầu bằng [Correction...]) thì bôi vàng
    if role == "👨‍🏫 Giám khảo" and "[Feedback]" in msg["content"]:
         st.warning(msg["content"])
    else:
         with st.chat_message(msg["role"]):
            st.write(msg["content"])

# Xử lý âm thanh chào mừng (chỉ chạy 1 lần đầu)
if "initial_audio" in st.session_state:
    text_to_speech(st.session_state.initial_audio)
    del st.session_state.initial_audio

st.write("---")

# --- 6. NÚT GHI ÂM (RESET KEY) ---
# Quan trọng: key=... giúp reset nút sau mỗi lần dùng
audio = audiorecorder("Nhấn để trả lời", "Đang ghi âm...", key=st.session_state.recorder_key)

if len(audio) > 0:
    # 1. STT
    user_text = speech_to_text(audio)
    
    if user_text:
        # Lưu lời thoại user
        st.session_state.chat_history.append({"role": "user", "content": user_text})
        
        # 2. Gửi cho AI
        with st.spinner("Giám khảo đang chấm điểm..."):
            response = st.session_state.chat.send_message(user_text)
            full_reply = response.text
            
        # 3. TÁCH PHẦN SỬA LỖI VÀ CÂU HỎI
        voice_content = full_reply # Mặc định là đọc hết
        
        if "|||" in full_reply:
            feedback_part, question_part = full_reply.split("|||")
            
            # Lưu phần Feedback (chỉ hiện chữ)
            st.session_state.chat_history.append({"role": "assistant", "content": f"[Feedback] {feedback_part.strip()}"})
            
            # Lưu phần Câu hỏi (để hiện và đọc)
            voice_content = question_part.strip()
            st.session_state.chat_history.append({"role": "assistant", "content": voice_content})
            
        else:
            # Không có lỗi
            st.session_state.chat_history.append({"role": "assistant", "content": full_reply})
            
        # 4. ĐỌC TO CÂU HỎI
        text_to_speech(voice_content)
        
        # 5. RESET NÚT GHI ÂM (Tăng key lên 1)
        st.session_state.recorder_key = str(int(st.session_state.recorder_key) + 1)
        
        # 6. Rerun để cập nhật giao diện
        st.rerun()
    else:
        st.error("Không nghe rõ. Vui lòng thử lại.")