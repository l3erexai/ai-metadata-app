import streamlit as st
import google.generativeai as genai
from PIL import Image
import io
import pandas as pd
import re # เพิ่มเข้ามาเพื่อช่วยแยกข้อมูล

# --- ตั้งค่าหน้า Streamlit ---
st.set_page_config(page_title="AI Image Analyzer", layout="wide")
st.title("🖼️ AI Image Analyzer (Titles & Tags)")
st.write("อัปโหลดรูปภาพ แล้ว AI จะช่วยคิดชื่อภาพ 5 แบบ และแท็ก 10 คำ")

# --- ใส่ API Key ---
api_key = st.text_input("ใส่ Google AI API Key ของคุณ:", type="password")

# --- ส่วนอัปโหลดรูปภาพ ---
uploaded_file = st.file_uploader("เลือกรูปภาพจากเครื่องของคุณ...", type=["jpg", "jpeg", "png"])

# --- ฟังก์ชันเรียก Gemini API ---
def get_gemini_response(api_key_input, image_data, prompt):
    """ส่งรูปภาพและ Prompt ไปยัง Gemini และรับผลลัพธ์กลับมา"""
    try:
        genai.configure(api_key=api_key_input)
        # เลือกโมเดลล่าสุดที่รองรับ Vision (อาจปรับเปลี่ยนตามรุ่นที่ Google แนะนำ)
        # gemini-1.5-flash เป็นตัวเลือกที่ดี รวดเร็วและรองรับ multimodal
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content([prompt, image_data])
        # ตรวจสอบว่ามี text ใน response หรือไม่
        if response.parts:
             return response.text
        else:
            # ลองตรวจสอบ candidate ถ้าโครงสร้าง response ต่างไป
            if response.candidates and response.candidates[0].content.parts:
                 return response.candidates[0].content.parts[0].text
            else:
                 return "ขออภัย ไม่สามารถดึงข้อความตอบกลับจาก API ได้"

    except Exception as e:
        return f"เกิดข้อผิดพลาดในการเรียก API: {e}"

# --- ฟังก์ชันแยก Title และ Tag จากข้อความ ---
def parse_gemini_output(text_output):
    """แยก Title และ Tag ออกจากข้อความตอบกลับของ Gemini"""
    titles = []
    tags = []

    # พยายามหา Titles (มองหาบรรทัดที่ขึ้นต้นด้วย Title:, 1., 2., -, * เป็นต้น)
    # ใช้ Regular Expression ช่วยหาบรรทัดที่มีลักษณะเป็นรายการ Title
    title_matches = re.findall(r"^(?:Title:|\*|\-|\d+\.?)\s*(.*)", text_output, re.MULTILINE | re.IGNORECASE)
    for match in title_matches:
        # ตัด "Tags:" หรือคำอื่นๆ ที่อาจปนมาออก
        if not match.lower().startswith("tags:"):
            cleaned_title = match.strip()
            if cleaned_title: # เช็คว่าไม่เป็นสตริงว่าง
                 titles.append(cleaned_title)

    # พยายามหา Tags (มองหาบรรทัดที่ขึ้นต้นด้วย Tags: หรือส่วนที่เป็น comma-separated)
    tag_match = re.search(r"Tags:\s*(.*)", text_output, re.IGNORECASE | re.DOTALL)
    if tag_match:
        tag_string = tag_match.group(1).strip()
        # แยกด้วย comma และเอาช่องว่างหัวท้ายออก
        tags = [tag.strip() for tag in tag_string.split(',') if tag.strip()]
    elif not tags and titles: # ถ้าหา Tags: ไม่เจอ ลองเดาว่าส่วนที่เหลือหลัง Titles คือ Tags
        lines = text_output.splitlines()
        potential_tag_line = ""
        found_titles_end = False
        for line in lines:
             if any(title in line for title in titles): # หาบรรทัดสุดท้ายของ title
                 found_titles_end = True
                 continue
             if found_titles_end and line.strip(): # เอาบรรทัดแรกหลัง title ที่ไม่ว่าง
                 potential_tag_line = line
                 break
        if potential_tag_line:
             tags = [tag.strip() for tag in potential_tag_line.split(',') if tag.strip()]


    # ถ้าจำนวน Title หรือ Tag เกิน ให้ตัดออกตามที่ขอ
    titles = titles[:5]
    tags = tags[:10]

    # ถ้าจำนวนน้อยกว่าที่ขอ อาจเติมค่าว่างเพื่อให้ตารางมีขนาดเท่ากัน
    while len(titles) < 5:
        titles.append("-")
    while len(tags) < 10:
        tags.append("-")

    return titles, tags

# --- ประมวลผลเมื่อมีการอัปโหลดรูปและใส่ API Key ---
if uploaded_file is not None and api_key:
    # แสดงรูปภาพที่อัปโหลด
    image = Image.open(uploaded_file)

    col1, col2 = st.columns(2) # แบ่งคอลัมน์เพื่อแสดงรูปและตาราง
    with col1:
        st.image(image, caption="รูปภาพที่อัปโหลด", use_column_width=True)

    # เตรียม Prompt สำหรับ Gemini (ขอจำนวนที่ต้องการ)
    prompt = f"""
    Analyze the image provided carefully. Generate the following based on the image content, style, and mood:

    1.  **Five (5) distinct title suggestions.** List each title clearly.
    2.  **Ten (10) relevant keywords or tags.** Provide them as a comma-separated list.

    Please format the output clearly, for example:
    Title: Suggestion 1
    Title: Suggestion 2
    ... (up to 5 titles)
    Tags: tag1, tag2, tag3, ... (up to 10 tags)
    """

    # แสดงสถานะกำลังทำงานและเรียก API
    st.markdown("---") # เส้นคั่น
    with st.spinner("🧠 AI กำลังวิเคราะห์รูปภาพและสร้างสรรค์ไอเดีย..."):
        gemini_result_text = get_gemini_response(api_key, image, prompt)

        if "เกิดข้อผิดพลาด" in gemini_result_text:
             st.error(gemini_result_text)
        elif "ไม่สามารถดึงข้อความ" in gemini_result_text:
             st.warning(gemini_result_text)
             st.text_area("Raw API Response:", gemini_result_text, height=150)
        else:
            # แยกผลลัพธ์
            suggested_titles, suggested_tags = parse_gemini_output(gemini_result_text)

            # สร้าง DataFrame สำหรับแสดงผล
            # ทำให้มีจำนวนแถวเท่ากันโดยเอาจำนวนสูงสุด (10 แถวสำหรับ tags)
            max_rows = max(len(suggested_titles), len(suggested_tags))
            display_data = {
                "ชื่อภาพที่แนะนำ (Suggested Titles)": (suggested_titles + ["-"] * (max_rows - len(suggested_titles)))[:max_rows],
                "แท็กที่เกี่ยวข้อง (Suggested Tags)": (suggested_tags + ["-"] * (max_rows - len(suggested_tags)))[:max_rows]
            }
            df = pd.DataFrame(display_data)

            # แสดงผลลัพธ์ในคอลัมน์ที่สอง
            with col2:
                st.subheader("✨ ผลลัพธ์จาก Gemini:")
                st.dataframe(df, use_container_width=True) # แสดง DataFrame

            # แสดง Raw output เผื่อ Debug
            with st.expander("ดูข้อความดิบที่ได้จาก Gemini"):
                 st.text(gemini_result_text)


elif uploaded_file is None:
    st.info("กรุณาอัปโหลดรูปภาพจากเครื่องของคุณ...")
elif not api_key:
    st.warning("กรุณาใส่ Google AI API Key ของคุณก่อน")

# --- หมายเหตุท้ายแอป ---
st.markdown("---")
st.caption("สร้างโดยใช้ Streamlit, Pandas และ Google Gemini API")