import streamlit as st
import google.generativeai as genai
from PIL import Image
import io
import pandas as pd
import re
from google.generativeai.types import StopCandidateException
from io import StringIO

# --- ตั้งค่าหน้า Streamlit ---
st.set_page_config(page_title="AI Metadata Exporter (Uses Secrets)", layout="wide") # เปลี่ยน Title
st.title("🖼️ AI Metadata Exporter (Reads API Key from Secrets)")
st.write("อัปโหลดหลายรูปภาพ -> กดปุ่ม 'เริ่มประมวลผล' -> แสดงผลรวม (1 แถว/ภาพ) -> ส่งออกเป็น CSV")

# --- !!! ส่วนจัดการ API Key ที่แก้ไขแล้ว !!! ---
api_key = None # กำหนดค่าเริ่มต้นเป็น None
try:
    # พยายามอ่าน Key จาก Secrets ที่ตั้งค่าใน Streamlit Cloud
    api_key = st.secrets["GOOGLE_API_KEY"]
    # (Optional) แสดงข้อความยืนยัน (แต่ซ่อน Key)
    st.caption("✔️ Google AI API Key loaded successfully from secrets.")
except KeyError:
    # ถ้าหา Key ใน Secrets ไม่เจอ (เช่น รันบนเครื่อง) ให้แสดงช่อง Input
    st.warning("⚠️ ไม่พบ Google API Key ใน Secrets. กรุณาใส่ด้านล่างเพื่อทดสอบ (หรือตั้งค่า Secrets ใน Streamlit Cloud):")
    api_key_input = st.text_input( # ใช้ตัวแปรชั่วคราว
        "ใส่ Google AI API Key ของคุณ:",
        type="password"
    )
    if api_key_input: # ถ้าผู้ใช้ป้อนค่าเข้ามา
        api_key = api_key_input
except Exception as e: # ดักจับ Error อื่นๆ ที่อาจเกิดจากการเข้าถึง Secrets
    st.error(f"เกิดข้อผิดพลาดในการโหลด API Key จาก Secrets: {e}")
    st.info("กรุณาตรวจสอบการตั้งค่า Secrets ใน Streamlit Cloud หรือลองใส่ Key ด้านล่าง:")
    api_key_input = st.text_input(
        "ใส่ Google AI API Key ของคุณ (สำรอง):",
        type="password"
    )
    if api_key_input:
        api_key = api_key_input

# --- ส่วนอัปโหลดหลายรูปภาพ ---
uploaded_files = st.file_uploader(
    "1. เลือกรูปภาพจากเครื่องของคุณ (เลือกได้หลายไฟล์)",
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True
)

# --- ปุ่มกดเริ่มการทำงาน ---
st.markdown("---")
process_button_clicked = st.button("🚀 2. เริ่มประมวลผลรูปภาพที่เลือก")
st.markdown("---")

# --- ฟังก์ชันเรียก Gemini API (ไม่ระบุ safety_settings) ---
def get_gemini_response(api_key_input, image_data, prompt):
    """ส่งรูปภาพและ Prompt ไปยัง Gemini และรับผลลัพธ์กลับมา (ไม่ระบุ safety_settings)"""
    # --- !!! ตรวจสอบ api_key_input ก่อน Configure !!! ---
    if not api_key_input:
        st.error("API Key ไม่ถูกต้องหรือไม่ถูกตั้งค่า")
        return None # คืนค่า None ถ้าไม่มี Key

    response = None
    try:
        genai.configure(api_key=api_key_input) # ใช้ Key ที่รับมา
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content([prompt, image_data])

        if response.candidates and hasattr(response.candidates[0], 'finish_reason') and response.candidates[0].finish_reason == 'SAFETY':
             return "API_SAFETY_BLOCK"

        if hasattr(response, 'text'):
            return response.text
        elif response.parts:
             return "".join(part.text for part in response.parts if hasattr(part, 'text'))
        elif response.candidates and response.candidates[0].content.parts:
             return "".join(part.text for part in response.candidates[0].content.parts if hasattr(part, 'text'))
        else:
            return "API_RESPONSE_ERROR"

    except StopCandidateException:
         return None
    except Exception as e:
         # แสดง Error ถ้าเกิด Exception ตอนเรียก API
         st.error(f"เกิดข้อผิดพลาดในการเรียก API (อาจเกี่ยวกับ Key หรืออื่นๆ): {e}")
         return None


# --- ฟังก์ชันแยก Title และ Keyword (ใช้เวอร์ชันล่าสุด v4) ---
def parse_gemini_metadata_v4(text_output):
    """แยก Titles และ Keywords จากข้อความตอบกลับ (v4 - ยืดหยุ่นขึ้น)"""
    titles = []
    keywords = []
    if not text_output or text_output == "API_SAFETY_BLOCK" or text_output == "API_RESPONSE_ERROR":
        return titles, keywords

    lines = text_output.strip().splitlines()
    keyword_line_index = -1
    keyword_string = ""

    for i, line in enumerate(lines):
        line_lower_stripped = line.strip().lower()
        if line_lower_stripped.startswith(("keywords:", "tags:", "keywords/tags:")) or \
           (line_lower_stripped.startswith("**") and ("keywords" in line_lower_stripped or "tags" in line_lower_stripped)):
            keyword_line_index = i
            keyword_string = re.sub(r"^\*{0,2}(?:Keywords/Tags|Keywords|Tags):\*{0,2}\s*", "", line.strip(), flags=re.IGNORECASE)
            break

    if keyword_string:
         keywords = [kw.strip() for kw in keyword_string.split(',') if kw.strip()][:20]

    if keyword_line_index != -1:
        for i in range(keyword_line_index):
            line_stripped = lines[i].strip()
            if not line_stripped or \
               line_stripped.lower().startswith(("here's an analysis", "**title suggestion")):
                continue
            cleaned_title = re.sub(r"^(?:Title:|\d+\.|\*|-)\s*", "", line_stripped, flags=re.IGNORECASE).strip()
            if cleaned_title and len(titles) < 10:
                titles.append(cleaned_title)
    elif not keywords and len(lines) > 1:
         last_line = lines[-1].strip()
         if ':' not in last_line and ',' in last_line and len(last_line.split(',')) > 2:
              keywords = [kw.strip() for kw in last_line.split(',') if kw.strip()][:20]
              for i in range(len(lines) - 1):
                   line_stripped = lines[i].strip()
                   if not line_stripped or \
                      line_stripped.lower().startswith(("here's an analysis", "**title suggestion")):
                       continue
                   cleaned_title = re.sub(r"^(?:Title:|\d+\.|\*|-)\s*", "", line_stripped, flags=re.IGNORECASE).strip()
                   if cleaned_title and len(titles) < 10:
                       titles.append(cleaned_title)

    if not titles:
         title_matches_fallback = re.findall(r"^Title:\s*(.*)", text_output, re.MULTILINE | re.IGNORECASE)
         if title_matches_fallback:
              titles = [match.strip() for match in title_matches_fallback][:10]

    return titles, keywords

# --- ฟังก์ชันสำหรับแปลง DataFrame เป็น CSV ---
@st.cache_data
def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf-8')

# --- ประมวลผลเมื่อกดปุ่ม ---
if process_button_clicked:
    # --- !!! ตรวจสอบ api_key ที่ได้จาก Secrets หรือ Input ก่อน !!! ---
    if not api_key:
         st.error("⛔ ไม่พบ Google AI API Key. กรุณาตั้งค่าใน Secrets หรือป้อนในช่องด้านบน")
    elif not uploaded_files:
         st.warning("⚠️ กรุณาอัปโหลดรูปภาพก่อนกดปุ่ม 'เริ่มประมวลผล'")
    else: # ถ้ามี Key และ มีไฟล์

        all_results_list = []
        error_files = []
        total_files = len(uploaded_files)
        progress_bar = st.progress(0, text="กำลังเตรียมประมวลผล...")

        for i, uploaded_file in enumerate(uploaded_files):
            filename = uploaded_file.name
            progress_text = f"กำลังประมวลผลไฟล์: {filename} ({i+1}/{total_files})..."
            progress_bar.progress((i + 1) / total_files, text=progress_text)

            try:
                image = Image.open(uploaded_file)
                prompt = f"""
                Analyze the provided image ({filename}) thoroughly. Generate:
                1.  Up to ten (10) diverse Title suggestions. List each on a new line.
                2.  Up to twenty (20) relevant Keywords/Tags as a comma-separated list, prefixed with "Keywords:".
                Example:
                Title Suggestion 1
                Title Suggestion 2
                Keywords: kw1, kw2, kw3
                """

                # --- !!! ส่ง api_key ที่อาจจะมาจาก Secrets หรือ Input !!! ---
                gemini_result_text = get_gemini_response(api_key, image, prompt)

                if gemini_result_text == "API_SAFETY_BLOCK":
                     st.warning(f"ไฟล์ '{filename}' ถูกบล็อกโดย Safety Filter")
                     error_files.append(f"{filename} (Safety Block)")
                     continue
                elif gemini_result_text == "API_RESPONSE_ERROR":
                     st.warning(f"ไฟล์ '{filename}' ไม่สามารถดึงข้อมูลจาก API ได้ถูกต้อง")
                     error_files.append(f"{filename} (API Response Error)")
                     continue
                elif gemini_result_text is None:
                     # Error แสดงไปแล้วใน get_gemini_response
                     error_files.append(f"{filename} (API Call Failed)")
                     continue
                else:
                    suggested_titles_list, suggested_keywords_list = parse_gemini_metadata_v4(gemini_result_text)
                    titles_str = ", ".join(suggested_titles_list) if suggested_titles_list else "-"
                    keywords_str = ", ".join(suggested_keywords_list) if suggested_keywords_list else "-"

                    all_results_list.append({
                        "Filename": filename,
                        "Title": titles_str,
                        "Keywords": keywords_str
                    })

            except Exception as e:
                st.error(f"เกิดข้อผิดพลาดในการประมวลผลไฟล์ '{filename}': {e}")
                error_files.append(f"{filename} (Processing Error: {e})")
                continue

        progress_bar.empty()

        if all_results_list:
            st.subheader("📊 ผลลัพธ์ Metadata รวม (1 แถวต่อไฟล์):")
            final_df = pd.DataFrame(all_results_list)
            st.dataframe(final_df, hide_index=True, use_container_width=True)
            csv_data = convert_df_to_csv(final_df)
            st.download_button(
               label="📥 ดาวน์โหลดผลลัพธ์เป็น CSV",
               data=csv_data,
               file_name='gemini_metadata_export.csv',
               mime='text/csv',
            )
        # --- !!! ย้ายการแจ้งเตือนกรณีไม่มีผลลัพธ์ มาหลังจาก Loop !!! ---
        elif not error_files: # ถ้าไม่มีผลลัพธ์ และไม่มี Error เลย (อาจจะไม่มีไฟล์อัปโหลดตั้งแต่แรก)
             st.info("กรุณาอัปโหลดไฟล์และกดปุ่ม 'เริ่มประมวลผล'")
        # กรณีมี Error แต่ไม่มีผลลัพธ์ จะแสดงรายชื่อไฟล์ Error ด้านล่าง

        if error_files:
             st.warning("ไฟล์ต่อไปนี้เกิดข้อผิดพลาด หรือถูกบล็อก:")
             for err_file in error_files:
                 st.markdown(f"- `{err_file}`")

# --- แสดงข้อความแนะนำเริ่มต้น (ถ้ายังไม่ได้กดปุ่มและยังไม่มีไฟล์) ---
elif not uploaded_files:
     st.info("กรุณาอัปโหลดรูปภาพ (เลือกได้หลายไฟล์) แล้วกดปุ่ม 'เริ่มประมวลผล'")

# --- หมายเหตุท้ายแอป ---
st.markdown("---")
st.caption("สร้างโดยใช้ Streamlit, Pandas และ Google Gemini API (Model: gemini-1.5-flash, Default Safety)")