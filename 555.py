import streamlit as st
import google.generativeai as genai
from openai import OpenAI, RateLimitError, APIError # Import OpenAI
from PIL import Image
import io
import pandas as pd
import re
from io import StringIO, BytesIO # Need BytesIO for base64 conversion
import time
from datetime import datetime, timedelta
import os
import base64 # Needed for OpenAI image encoding

# --- ตั้งค่าหน้า Streamlit ---
st.set_page_config(page_title="AI Metadata Processor v2.3", layout="wide") # Increment version
st.title("🖼️ AI Metadata Processor v2.3 (Multi-Provider: Gemini & OpenAI)")
st.write("อัปโหลดรูปภาพ, กำหนดค่า, เลือก API Provider และ Model, เลือกโหมด, ประมวลผล, และส่งออก CSV")

# --- ชื่อไฟล์ CSV ชั่วคราว ---
TEMP_CSV_FILENAME = "temp_metadata_incremental_v2.csv"

# --- ส่วนจัดการ API Keys ---
st.sidebar.subheader("🔑 API Keys")
google_api_key = None
openai_api_key = None

# Google API Key
try:
    google_api_key = st.secrets["GOOGLE_API_KEY"]
    st.sidebar.caption("✔️ Google API Key loaded from secrets.")
except (KeyError, FileNotFoundError):
    st.sidebar.warning("⚠️ ไม่พบ Google API Key ใน Secrets.")
    google_api_key_input = st.sidebar.text_input("ใส่ Google AI API Key:", type="password", key="google_api_key_input")
    if google_api_key_input: google_api_key = google_api_key_input

# OpenAI API Key
try:
    openai_api_key = st.secrets["OPENAI_API_KEY"]
    st.sidebar.caption("✔️ OpenAI API Key loaded from secrets.")
except (KeyError, FileNotFoundError):
    st.sidebar.warning("⚠️ ไม่พบ OpenAI API Key ใน Secrets.")
    openai_api_key_input = st.sidebar.text_input("ใส่ OpenAI API Key:", type="password", key="openai_api_key_input")
    if openai_api_key_input: openai_api_key = openai_api_key_input

# --- เลือก API Provider ---
st.sidebar.subheader("🤖 เลือก AI Provider")
api_provider = st.sidebar.radio(
    "เลือกบริการ AI:",
    options=["Google Gemini", "OpenAI GPT"],
    index=0,
    key="api_provider_selector"
)
st.sidebar.caption(f"Provider ที่เลือก: **{api_provider}**")

# --- ส่วนอัปโหลดหลายรูปภาพ ---
st.subheader("1. อัปโหลดรูปภาพ")
uploaded_files = st.file_uploader(
    "เลือกรูปภาพ (ต้องอัปโหลดรูปภาพเสมอ)",
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True,
    key="file_uploader"
)

if uploaded_files:
    num_files_uploaded = len(uploaded_files)
    st.success(f"✅ คุณได้เลือกรูปภาพแล้วทั้งหมด: {num_files_uploaded} ภาพ")
else:
    st.info("💡 ยังไม่ได้เลือกรูปภาพ")

# --- ส่วนกำหนดค่า ---
st.markdown("---")
st.subheader("2. กำหนดค่าการประมวลผล")
col_config1, col_config2, col_config3 = st.columns(3)
with col_config1:
    num_titles_req = st.number_input(
        "จำนวนชื่อภาพ (Titles):", min_value=1, value=5, step=1,
        help="AI จะพยายามสร้างให้ได้มากที่สุดไม่เกินจำนวนนี้"
    )
with col_config2:
    num_keywords_req = st.number_input(
        "จำนวน Keywords/Tags:", min_value=1, value=20, step=1,
        help="AI จะพยายามสร้างให้ได้มากที่สุดไม่เกินจำนวนนี้"
    )

# --- Model Selection (Conditional based on provider) ---
selected_model_name = None
with col_config3:
    st.write(f"**เลือก Model ({api_provider}):**")
    if api_provider == "Google Gemini":
        available_models = ['gemini-1.5-flash', 'gemini-pro-vision'] # Add more if needed
        selected_model_name = st.selectbox(
            "Gemini Model:",
            options=available_models,
            index=0,
            key="gemini_model_selector",
            label_visibility="collapsed"
        )
    elif api_provider == "OpenAI GPT":
        # Use models capable of vision, like gpt-4o or gpt-4-vision-preview
        available_models = ['gpt-4o', 'gpt-4-vision-preview'] # Update as needed
        selected_model_name = st.selectbox(
            "OpenAI Model:",
            options=available_models,
            index=0, # Default to gpt-4o if available
            key="openai_model_selector",
            label_visibility="collapsed"
        )
    st.caption(f"Model: `{selected_model_name}`")

# --- ส่วนเลือกโหมดการทำงาน ---
st.markdown("---")
st.subheader("3. เลือกโหมดการทำงาน")
processing_mode = st.radio(
    "เลือกวิธีประมวลผล:",
    options=[
        f"ประมวลผลไฟล์ใหม่ / ทำต่อจากไฟล์ชั่วคราว ({TEMP_CSV_FILENAME})",
        "แก้ไขข้อมูลที่ขาดหายจากไฟล์ CSV ที่อัปโหลด (พร้อม Retry)"
    ],
    index=0,
    key="processing_mode_radio"
)

# --- ช่องอัปโหลด CSV (แสดงเฉพาะโหมดแก้ไข) ---
existing_csv_file = None
if "แก้ไขข้อมูลที่ขาดหาย" in processing_mode:
    existing_csv_file = st.file_uploader(
        "อัปโหลดไฟล์ CSV เดิม (*ต้อง* มี 'Filename', 'Title', 'Keywords')",
        type=["csv"],
        key="csv_uploader"
    )
    if existing_csv_file:
        st.info("พร้อมสำหรับโหมดแก้ไข CSV (เมื่อกดปุ่มเริ่ม)")
    else:
        st.warning("กรุณาอัปโหลดไฟล์ CSV เดิมเพื่อใช้โหมดแก้ไข")


# --- ปุ่มกดเริ่มการทำงาน ---
st.markdown("---")
col_buttons1, col_buttons2 = st.columns([3,1])
with col_buttons1:
    button_label = f"🚀 เริ่มประมวลผล ({api_provider})"
    if "แก้ไขข้อมูลที่ขาดหาย" in processing_mode:
        button_label = f"🔄 เริ่มแก้ไขข้อมูลจาก CSV ({api_provider})"
    process_button_clicked = st.button(button_label, use_container_width=True, key="process_button")

# Add Clear button
with col_buttons2:
    if st.button(f"🗑️ Clear {TEMP_CSV_FILENAME}", help=f"ลบไฟล์ {TEMP_CSV_FILENAME}", key="clear_button"):
        # ... (Clear logic - same as before) ...
        if os.path.exists(TEMP_CSV_FILENAME):
            try:
                os.remove(TEMP_CSV_FILENAME)
                st.success(f"{TEMP_CSV_FILENAME} cleared successfully!")
            except Exception as e:
                st.error(f"ไม่สามารถลบ {TEMP_CSV_FILENAME}: {e}")
        else:
            st.info(f"{TEMP_CSV_FILENAME} does not exist.")

st.markdown("---")

# --- Helper Function: PIL Image to Base64 ---
def pil_to_base64(image, format="JPEG"):
    buffered = BytesIO()
    image.save(buffered, format=format)
    img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
    return f"data:image/{format.lower()};base64,{img_str}"

# --- ฟังก์ชันเรียก Google Gemini API ---
def get_gemini_response(api_key_input, image_pil, prompt, model_name):
    if not api_key_input: return "API_KEY_MISSING" # Return specific code
    # ... (Gemini API call logic - same as v2.2) ...
    response = None
    try:
        time.sleep(5)
        genai.configure(api_key=api_key_input)
        model = genai.GenerativeModel(model_name)
        response = model.generate_content([prompt, image_pil])

        if response.prompt_feedback and response.prompt_feedback.block_reason:
             return "API_SAFETY_BLOCK"
        if not (hasattr(response, 'text') or response.parts or (response.candidates and response.candidates[0].content and response.candidates[0].content.parts)):
             if response.candidates and hasattr(response.candidates[0], 'finish_reason') and response.candidates[0].finish_reason == 'SAFETY':
                 return "API_SAFETY_BLOCK"

        if hasattr(response, 'text'): return response.text
        elif response.parts: return "".join(part.text for part in response.parts if hasattr(part, 'text'))
        elif response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
             return "".join(part.text for part in response.candidates[0].content.parts if hasattr(part, 'text'))
        else: return "API_RESPONSE_ERROR"
    except Exception as e:
        if "429" in str(e) or "Resource has been exhausted" in str(e) or "rate limit" in str(e).lower():
            st.warning(f"⏳ Gemini Rate Limit (Model: {model_name}). Waiting 60s...")
            time.sleep(61)
            return get_gemini_response(api_key_input, image_pil, prompt, model_name)
        # print(f"Error in get_gemini_response (Model: {model_name}): {type(e).__name__}: {e}")
        return "API_CALL_ERROR"


# --- ฟังก์ชันเรียก OpenAI GPT API ---
def get_openai_response(api_key_input, image_pil, prompt, model_name):
    if not api_key_input: return "API_KEY_MISSING" # Return specific code
    try:
        time.sleep(1) # Shorter delay for OpenAI? Test this.
        client = OpenAI(api_key=api_key_input)

        # Convert PIL image to base64
        base64_image = pil_to_base64(image_pil)

        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": base64_image},
                        },
                    ],
                }
            ],
            max_tokens=500 # Adjust max_tokens as needed for titles/keywords
        )
        # print("DEBUG OpenAI Full Response:", response) # Uncomment for debugging

        if response.choices and response.choices[0].message and response.choices[0].message.content:
             # Check for potential content filter issues (less explicit than Gemini)
             finish_reason = response.choices[0].finish_reason
             if finish_reason == 'content_filter':
                 return "API_SAFETY_BLOCK" # Treat content filter as safety block
             return response.choices[0].message.content.strip()
        else:
            return "API_RESPONSE_ERROR"

    except RateLimitError as e:
        st.warning(f"⏳ OpenAI Rate Limit (Model: {model_name}). Waiting 60s...")
        # print(f"OpenAI RateLimitError: {e}")
        time.sleep(61)
        return get_openai_response(api_key_input, image_pil, prompt, model_name) # Retry
    except APIError as e:
        # print(f"OpenAI APIError (Model: {model_name}): {type(e).__name__} - {e}")
        # Handle specific API errors if needed (e.g., invalid request, server error)
        return "API_CALL_ERROR" # General API call error
    except Exception as e: # Catch other potential errors
        # print(f"Error in get_openai_response (Model: {model_name}): {type(e).__name__}: {e}")
        return "API_CALL_ERROR"

# --- ฟังก์ชันแยก Title และ Keyword (V6 - Reused for both providers initially) ---
# Note: This might need adjustments after testing OpenAI's output format.
def parse_metadata_v6(text_output, requested_titles, requested_keywords):
    # ... (Parser logic - same as parse_gemini_metadata_v6) ...
    titles = []
    keywords = []
    if not text_output or text_output in ["API_SAFETY_BLOCK", "API_RESPONSE_ERROR", "API_CALL_ERROR", "API_KEY_MISSING", "API_EMPTY_RESPONSE", "FAILED_RETRY", "SAFETY_BLOCKED"]: # Added more potential error codes
        return titles, keywords

    lines = text_output.strip().splitlines()
    keyword_line_index = -1
    keyword_string_raw = ""

    keyword_patterns = [
        r"^\**\s*(?:keywords/tags|keywords|tags)\s*:\**\s*(.*)",
        r"^\s*-\s*(?:keywords|tags):\s*(.*)",
    ]

    for i, line in enumerate(lines):
        line_stripped = line.strip()
        if not line_stripped: continue
        for pattern in keyword_patterns:
            match = re.match(pattern, line_stripped, re.IGNORECASE)
            if match:
                keyword_string_raw = match.group(1).strip()
                keyword_line_index = i
                break
        if keyword_line_index != -1: break

    if keyword_string_raw and keyword_string_raw != "-":
        keyword_string_cleaned = re.sub(r'^\**\s*(?:keywords/tags|keywords|tags)\s*:\**\s*', '', keyword_string_raw, flags=re.IGNORECASE).strip()
        keyword_string_cleaned = re.sub(r'^\*+|\*+$', '', keyword_string_cleaned).strip()
        keywords = [kw.strip() for kw in keyword_string_cleaned.split(',') if kw.strip() and len(kw.strip()) > 1]
        keywords = keywords[:requested_keywords]

    title_limit = keyword_line_index if keyword_line_index != -1 else len(lines)
    for i in range(title_limit):
        line_stripped = lines[i].strip()
        is_likely_header = re.match(r"^\**\s*(?:Titles?|Suggestions?|Analysis)\s*:?\**$", line_stripped, re.IGNORECASE)
        is_likely_keyword_line = (keyword_line_index != -1 and i == keyword_line_index)
        if not line_stripped or line_stripped == "-" or is_likely_header or is_likely_keyword_line or line_stripped.lower().startswith("here are") or re.match(r"^\d+\.\s*$", line_stripped):
            continue
        cleaned_title = re.sub(r"^\**\s*\d+\.\s*", "", line_stripped)
        cleaned_title = re.sub(r"^\**\s*(?:Title|Suggestion)\s*[:\-]?\**\s*", "", cleaned_title, flags=re.IGNORECASE)
        cleaned_title = re.sub(r"\**$", "", cleaned_title).strip()
        if cleaned_title and cleaned_title != "-" and len(titles) < requested_titles:
            if cleaned_title.lower() not in [kw.lower() for kw in keywords]:
                 titles.append(cleaned_title)

    if not keywords and keyword_line_index == -1:
        for line in reversed(lines):
            line_stripped = line.strip()
            if ',' in line_stripped and line_stripped.count(',') >= 2 and not any(word in line_stripped.lower() for word in ['title', 'suggestion', 'analysis', 'generated by', 'http', 'www']):
                potential_keywords = [kw.strip() for kw in line_stripped.split(',') if kw.strip() and len(kw.strip()) > 1]
                if len(potential_keywords) >= 3 :
                    keywords = potential_keywords[:requested_keywords]
                    break
    return titles, keywords


# --- ฟังก์ชันสำหรับแปลง DataFrame เป็น CSV ---
@st.cache_data
def convert_df_to_csv(df):
    return df.to_csv(index=False, encoding='utf-8').encode('utf-8')

# --- ประมวลผลเมื่อกดปุ่ม ---
if process_button_clicked:
    # --- Input Validation (Check selected provider's key) ---
    provider_key_missing = False
    if api_provider == "Google Gemini" and not google_api_key:
        st.error("⛔ ไม่พบ Google AI API Key. กรุณาใส่ API Key ใน Sidebar.")
        provider_key_missing = True
    elif api_provider == "OpenAI GPT" and not openai_api_key:
        st.error("⛔ ไม่พบ OpenAI API Key. กรุณาใส่ API Key ใน Sidebar.")
        provider_key_missing = True

    if provider_key_missing or not uploaded_files or ("แก้ไขข้อมูลที่ขาดหาย" in processing_mode and not existing_csv_file):
        if not uploaded_files: st.warning("⚠️ กรุณาอัปโหลดรูปภาพก่อน")
        if "แก้ไขข้อมูลที่ขาดหาย" in processing_mode and not existing_csv_file: st.error("⛔ กรุณาอัปโหลดไฟล์ CSV เดิมสำหรับโหมดแก้ไข")
        st.stop()
    # --- End Input Validation ---

    start_time_total = time.time()
    error_files = []
    final_df = pd.DataFrame()
    results_placeholder = st.empty()
    status_placeholder = st.empty()
    results_list = []

    # --- กำหนด Prompt (Same template used for both) ---
    base_prompt_template = f"""Analyze the image provided ({{filename}}). Strictly follow these instructions:
1. Generate up to {num_titles_req} distinct and relevant Titles for the image. Each title MUST be on a new line. Avoid generic titles.
2. Generate up to {num_keywords_req} relevant, comma-separated Keywords describing the image content, style, concepts, and potential use cases. This section is REQUIRED. Start the keyword line explicitly with 'Keywords:'. Example format: Keywords: word1, word2, word3, word4
DO NOT output '-' for keywords unless the image is completely blank or unrecognizable. Prioritize generating meaningful keywords."""

    # Determine API key and function based on provider
    api_key_to_use = google_api_key if api_provider == "Google Gemini" else openai_api_key
    api_function = get_gemini_response if api_provider == "Google Gemini" else get_openai_response
    provider_tag = "Gemini" if api_provider == "Google Gemini" else "OpenAI" # Short tag for messages

    # --- โหมดปกติ ---
    if "ประมวลผลไฟล์ใหม่" in processing_mode:
        status_placeholder.info(f"โหมดปกติ: กำลังประมวลผล ({provider_tag}: {selected_model_name}) และเขียน/อัปเดต {TEMP_CSV_FILENAME}")
        # ... (Load existing data logic - same as v2.2) ...
        processed_filenames = set()
        if os.path.exists(TEMP_CSV_FILENAME):
             try: # Read/init existing data
                 existing_df_temp = pd.read_csv(TEMP_CSV_FILENAME, encoding='utf-8', keep_default_na=False, na_values=[''])
                 existing_df_temp = existing_df_temp.fillna('-').astype(str)
                 results_list = existing_df_temp.to_dict('records')
                 processed_filenames = set(existing_df_temp.iloc[:, 0].unique())
                 st.success(f"พบข้อมูลเก่า {len(processed_filenames)} ไฟล์ใน {TEMP_CSV_FILENAME}. ทำต่อ...")
             except Exception as e: # Handle errors during load
                 st.warning(f"ไม่สามารถอ่าน {TEMP_CSV_FILENAME}: {e}. สร้างใหม่.")
                 processed_filenames, results_list = set(), []
        else: results_list = [] # Start fresh if no file

        files_to_process_list = [f for f in uploaded_files if f.name not in processed_filenames]
        total_files_to_process = len(files_to_process_list)

        if total_files_to_process == 0 and processed_filenames:
             st.info("✅ ไฟล์ที่อัปโหลดทั้งหมดถูกประมวลผลไปแล้ว.")
             if results_list: final_df = pd.DataFrame(results_list)

        elif total_files_to_process > 0:
            st.info(f"จะประมวลผล {total_files_to_process} ไฟล์ใหม่ ({provider_tag}: {selected_model_name})...")
            progress_bar = st.progress(0, text="...")
            current_new_file_index = 0

            for uploaded_file in files_to_process_list:
                filename = uploaded_file.name
                current_new_file_index += 1
                # ... (Update progress bar & time calculation - same as v2.2, add provider/model) ...
                progress_text = f"ประมวลผล: {filename} ({current_new_file_index}/{total_files_to_process})"
                progress_percentage = current_new_file_index / total_files_to_process
                progress_bar.progress(progress_percentage, text=progress_text)
                # Time calc ...
                current_time = time.time(); elapsed_time = current_time - start_time_total
                avg_time_per_file = elapsed_time / current_new_file_index if current_new_file_index > 0 else 0
                files_remaining = total_files_to_process - current_new_file_index
                estimated_time_remaining = avg_time_per_file * files_remaining if avg_time_per_file > 0 else 0
                estimated_completion_time = datetime.now() + timedelta(seconds=estimated_time_remaining)
                elapsed_str = str(timedelta(seconds=int(elapsed_time)))
                remaining_str = str(timedelta(seconds=int(estimated_time_remaining))) if estimated_time_remaining > 0 else "--:--:--"
                eta_str = estimated_completion_time.strftime("%H:%M:%S") if estimated_time_remaining > 0 else "N/A"
                status_placeholder.info(f"⏱️ เวลา: {elapsed_str} | เหลือ: {remaining_str} | เสร็จ: {eta_str} ({avg_time_per_file:.2f} วิ/ภาพ) | {provider_tag}: {selected_model_name}")

                try:
                    image = Image.open(uploaded_file)
                    if image.mode != 'RGB': image = image.convert('RGB')
                    prompt = base_prompt_template.format(filename=filename)

                    # --- Call the selected API function ---
                    result_text = api_function(api_key_to_use, image, prompt, selected_model_name)

                    titles_str = "-"
                    keywords_str = "-"
                    # --- Process result (handle error codes) ---
                    if result_text == "API_KEY_MISSING":
                        st.error(f"⛔ API Key for {api_provider} is missing. Stopping.")
                        st.stop() # Stop processing if key is missing mid-way
                    elif result_text == "API_SAFETY_BLOCK":
                        error_files.append(f"{filename} (Safety Block)")
                        keywords_str = "SAFETY_BLOCKED"
                    elif result_text == "API_RESPONSE_ERROR":
                        error_files.append(f"{filename} (API Response Error)")
                        keywords_str = "API_RESPONSE_ERROR"
                    elif result_text == "API_CALL_ERROR":
                         error_files.append(f"{filename} (API Call Failed)")
                         keywords_str = "API_CALL_ERROR"
                    elif result_text:
                        # --- Use the unified parser ---
                        suggested_titles_list, suggested_keywords_list = parse_metadata_v6(result_text, num_titles_req, num_keywords_req)
                        titles_str = ", ".join(suggested_titles_list) if suggested_titles_list else "-"
                        keywords_str = ", ".join(suggested_keywords_list) if suggested_keywords_list else "-"
                        if not suggested_keywords_list or keywords_str.strip() == "-":
                            keywords_str = "-"

                    result_dict = {"Filename": filename, "Title": titles_str, "Keywords": keywords_str}
                    results_list.append(result_dict)

                    # ... (Write to temp file & update display logic - same as v2.2) ...
                    temp_df_single = pd.DataFrame([result_dict])
                    write_header = not os.path.exists(TEMP_CSV_FILENAME) or os.path.getsize(TEMP_CSV_FILENAME) == 0
                    try: temp_df_single.to_csv(TEMP_CSV_FILENAME, mode='a', header=write_header, index=False, encoding='utf-8')
                    except Exception as write_e: st.error(f"Error writing to {TEMP_CSV_FILENAME} for {filename}: {write_e}")
                    if results_list:
                        current_display_df = pd.DataFrame(results_list)
                        results_placeholder.dataframe(current_display_df.tail(10), hide_index=True, use_container_width=True)

                except Exception as e:
                    error_msg = f"Processing Error: {type(e).__name__}: {e}"
                    error_files.append(f"{filename} ({error_msg})")
                    results_list.append({"Filename": filename, "Title": "-", "Keywords": f"ERROR: {error_msg}"})
                    continue # Continue to the next file

            progress_bar.empty()
            status_placeholder.success(f"🎉 ประมวลผล {total_files_to_process} ไฟล์ใหม่เสร็จสิ้น ({provider_tag}) ใน {str(timedelta(seconds=int(time.time() - start_time_total)))}!")
            if results_list: final_df = pd.DataFrame(results_list)


    # --- โหมดแก้ไข ---
    elif "แก้ไขข้อมูลที่ขาดหาย" in processing_mode:
        status_placeholder.info(f"โหมดแก้ไข: กำลังอ่าน CSV, หาข้อมูลขาดหาย, และ Retry ({provider_tag}: {selected_model_name})...")
        # ... (CSV Reading and finding rows logic - same as v2.1) ...
        existing_df = None; rows_to_rerun_index = pd.Index([])
        try: # Read CSV and find rows to rerun
             existing_df = pd.read_csv(existing_csv_file, encoding='utf-8', keep_default_na=False, na_values=[''])
             if not all(col in existing_df.columns for col in ["Filename", "Title", "Keywords"]):
                 st.error("⛔ CSV ไม่มีคอลัมน์ 'Filename', 'Title', 'Keywords'.")
                 existing_df = None
             else:
                 if 'Title' in existing_df.columns: existing_df['Title'] = existing_df['Title'].fillna('-')
                 if 'Keywords' in existing_df.columns: existing_df['Keywords'] = existing_df['Keywords'].fillna('-')
                 existing_df = existing_df.astype(str)
                 rows_to_rerun_index = existing_df[(existing_df['Title'].str.strip().isin(['-', ''])) | (existing_df['Keywords'].str.strip().isin(['-', '']))].index
                 filenames_to_rerun = existing_df.loc[rows_to_rerun_index, 'Filename'].tolist()
        except Exception as e: # Handle read errors
             st.error(f"เกิดข้อผิดพลาดในการอ่าน CSV: {type(e).__name__}: {e}")
             existing_df = None

        if existing_df is not None and not rows_to_rerun_index.empty:
            st.info(f"พบ {len(rows_to_rerun_index)} แถวต้องการแก้ไข ({provider_tag}: {selected_model_name})...")
            # ... (Setup for rerun - same as v2.2) ...
            uploaded_file_map = {f.name: f for f in uploaded_files}
            processed_count_rerun = 0
            total_files_to_rerun = len(rows_to_rerun_index)
            progress_bar = st.progress(0, text="...")
            updated_df = existing_df.copy()
            results_list_rerun = []

            for idx in rows_to_rerun_index:
                filename = updated_df.loc[idx, 'Filename']
                # ... (Check image exists, update progress/time - same as v2.2, add provider/model) ...
                if filename not in uploaded_file_map: # Skip if image missing
                     st.warning(f"⚠️ ไม่พบภาพ '{filename}' -> ข้าม")
                     error_files.append(f"{filename} (Missing Image for Rerun)")
                     results_list_rerun.append(updated_df.loc[idx].to_dict())
                     continue
                processed_count_rerun += 1
                # Progress bar & time calc ...
                progress_text = f"แก้ไข: {filename} ({processed_count_rerun}/{total_files_to_rerun})"
                progress_percentage = processed_count_rerun / total_files_to_rerun
                progress_bar.progress(progress_percentage, text=progress_text)
                current_time = time.time(); elapsed_time = current_time - start_time_total
                avg_time_per_file = elapsed_time / processed_count_rerun if processed_count_rerun > 0 else 0
                files_remaining = total_files_to_rerun - processed_count_rerun
                estimated_time_remaining = avg_time_per_file * files_remaining if avg_time_per_file > 0 else 0
                estimated_completion_time = datetime.now() + timedelta(seconds=estimated_time_remaining)
                elapsed_str = str(timedelta(seconds=int(elapsed_time)))
                remaining_str = str(timedelta(seconds=int(estimated_time_remaining))) if estimated_time_remaining > 0 else "--:--:--"
                eta_str = estimated_completion_time.strftime("%H:%M:%S") if estimated_time_remaining > 0 else "N/A"
                status_placeholder.info(f"⏱️ เวลา: {elapsed_str} | เหลือ: {remaining_str} | เสร็จ: {eta_str} ({avg_time_per_file:.2f} วิ/ภาพ) | {provider_tag}: {selected_model_name}")


                try:
                    uploaded_file = uploaded_file_map[filename]
                    image = Image.open(uploaded_file)
                    if image.mode != 'RGB': image = image.convert('RGB')
                    prompt = base_prompt_template.format(filename=filename)

                    # --- Retry Logic ---
                    result_text = None
                    is_metadata_ok = False
                    max_retries = 2
                    retry_count = 0
                    final_titles_str = updated_df.loc[idx, 'Title'] # Keep original
                    final_keywords_str = updated_df.loc[idx, 'Keywords'] # Keep original
                    last_error = None

                    while retry_count <= max_retries:
                        if retry_count > 0:
                            st.warning(f"🔄 Retrying '{filename}' ({retry_count+1}/{max_retries+1})...")

                        # --- Call the selected API function ---
                        result_text = api_function(api_key_to_use, image, prompt, selected_model_name)
                        last_error = result_text # Store last status/error

                        # --- Process result within retry loop ---
                        if result_text == "API_KEY_MISSING": st.stop() # Stop if key missing
                        elif result_text == "API_SAFETY_BLOCK":
                            error_files.append(f"{filename} (Safety Block attempt {retry_count+1})")
                            final_keywords_str = "SAFETY_BLOCKED"; break
                        elif result_text in ["API_RESPONSE_ERROR", "API_CALL_ERROR"]:
                            error_files.append(f"{filename} ({result_text} attempt {retry_count+1})")
                            if retry_count >= max_retries: final_keywords_str = result_text
                        elif result_text:
                            # --- Use the unified parser ---
                            temp_titles_list, temp_keywords_list = parse_metadata_v6(result_text, num_titles_req, num_keywords_req)
                            if temp_keywords_list: # Success condition: got keywords
                                is_metadata_ok = True
                                final_titles_str = ", ".join(temp_titles_list) if temp_titles_list else "-"
                                final_keywords_str = ", ".join(temp_keywords_list)
                                break # Exit retry loop on success
                            else: pass # Retry if keywords still empty
                        else: # Handle empty response
                            error_files.append(f"{filename} (Empty API Response attempt {retry_count+1})")
                            last_error = "API_EMPTY_RESPONSE"
                            if retry_count >= max_retries: final_keywords_str = last_error

                        retry_count += 1
                    # --- End while retry ---

                    if not is_metadata_ok:
                        st.error(f"❌ Failed keywords for '{filename}' after {max_retries+1} attempts. Last status: {last_error or 'Unknown'}.")
                        if final_keywords_str.strip() == '-' or final_keywords_str.strip() == '':
                           final_keywords_str = "FAILED_RETRY"

                    # --- Update DataFrame and display ---
                    updated_df.loc[idx, 'Title'] = final_titles_str
                    updated_df.loc[idx, 'Keywords'] = final_keywords_str
                    results_list_rerun.append({"Filename": filename, "Title": final_titles_str, "Keywords": final_keywords_str})
                    if results_list_rerun:
                         current_rerun_display_df = pd.DataFrame(results_list_rerun)
                         results_placeholder.dataframe(current_rerun_display_df.tail(10), hide_index=True, use_container_width=True)

                except Exception as e: # Catch processing errors outside API call
                    error_msg = f"Rerun Processing Error: {type(e).__name__}: {e}"
                    error_files.append(f"{filename} ({error_msg})")
                    updated_df.loc[idx, 'Keywords'] = f"ERROR: {error_msg}"
                    results_list_rerun.append(updated_df.loc[idx].to_dict())
                    continue # Continue to next file

            progress_bar.empty()
            status_placeholder.success(f"🎉 แก้ไข {processed_count_rerun} รายการเสร็จสิ้น ({provider_tag}) ใน {str(timedelta(seconds=int(time.time() - start_time_total)))}!")
            final_df = updated_df

        elif existing_df is not None and rows_to_rerun_index.empty:
            st.success("✅ ไม่พบข้อมูลที่ขาดหายใน CSV.")
            final_df = existing_df

    # --- ส่วนแสดงผลลัพธ์และดาวน์โหลด ---
    st.markdown("---")
    st.subheader("📊 ผลลัพธ์ Metadata:")
    if not final_df.empty:
        st.dataframe(final_df, hide_index=True, use_container_width=True)
        csv_data = convert_df_to_csv(final_df)
        # Include provider and model in filename
        provider_short = "gemini" if api_provider == "Google Gemini" else "openai"
        model_short = selected_model_name.replace("gemini-", "").replace("gpt-", "") # Shorter model name
        mode_tag = 'rerun_final' if 'แก้ไขข้อมูลที่ขาดหาย' in processing_mode else 'export'
        csv_filename = f"metadata_{provider_short}_{model_short}_{mode_tag}.csv"
        st.download_button(
           label=f"📥 ดาวน์โหลดผลลัพธ์ ({provider_tag}: {selected_model_name}) เป็น CSV",
           data=csv_data,
           file_name=csv_filename,
           mime='text/csv',
           key="download_button"
        )
    # ... (Handle no results / errors display - same as v2.2) ...
    elif not error_files and process_button_clicked:
         status_placeholder.info("ไม่มีผลลัพธ์ให้แสดง.")
    elif error_files and final_df.empty:
         status_placeholder.warning("ประมวลผลเสร็จสิ้น แต่ไม่มี DataFrame สุดท้าย.")

    if error_files: # Display errors
         st.warning("⚠️ ไฟล์/รายการต่อไปนี้เกิดข้อผิดพลาด:")
         # ... (Error display logic - same as v2.2) ...
         error_summary = {}
         for error_msg in error_files:
             match = re.match(r"^(.*?)\s+\((.*?)\)$", error_msg)
             if match:
                 fname, etype = match.groups(); etype = re.sub(r' attempt \d+', '', etype).strip()
                 if etype not in error_summary: error_summary[etype] = []
                 error_summary[etype].append(fname)
             else:
                 etype = "Unknown Error"
                 if etype not in error_summary: error_summary[etype] = []
                 error_summary[etype].append(error_msg)
         for etype, fnames in error_summary.items():
              with st.expander(f"{etype} ({len(fnames)} รายการ)", expanded=False):
                   if len(fnames) > 10:
                       num_cols=3; cols=st.columns(num_cols)
                       for i, fname in enumerate(fnames): cols[i%num_cols].code(fname, language=None)
                   else: st.json({i+1: fname for i,fname in enumerate(fnames)})


# --- Footer ---
st.markdown("---")
st.caption(f"สร้างโดยใช้ Streamlit, Pandas | Provider: {api_provider} | Model: {selected_model_name}")