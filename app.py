import streamlit as st
from streamlit_option_menu import option_menu
import numpy as np
import cv2
import re
import easyocr
import tensorflow as tf
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import firebase_admin
from firebase_admin import credentials, db, auth
import tf_keras

cred = credentials.Certificate('key.json')
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://businesscard-ocr-8ff65-default-rtdb.asia-southeast1.firebasedatabase.app/' 
    })

model = tf_keras.models.load_model('business_card_classifier.h5')

scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
         "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
client = gspread.authorize(creds)

def signup(email, password):
    try:
        user = auth.create_user(email=email, password=password)
        st.session_state['user'] = {'localId': user.uid, 'email': email}
        st.success("Sign up successful! Please log in.")
    except Exception as e:
        st.error(f"Sign up error: {e}")

def login(email, password):
    try:
        user = auth.get_user_by_email(email)
        st.session_state['user'] = {'localId': user.uid, 'email': email}
        st.success("Login successful!")
        st.experimental_rerun()
    except Exception as e:
        st.error(f"Login error: {e}")

def logout():
    if 'user' in st.session_state:
        del st.session_state['user']
        st.success("Logged out successfully.")
        st.experimental_rerun()

def predict_image_orientation(image):
    resized_image = cv2.resize(image, (224, 224))
    img_array = np.array(resized_image) / 255.0
    img_array = np.expand_dims(img_array, axis=0)
    prediction = model.predict(img_array)
    return 'straight' if prediction < 0.5 else 'not_straight'

def rotate_image_if_needed(image, orientation):
    if orientation == 'not_straight':
        rotated_image = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
        return rotated_image
    return image

def extract_text_from_image(image):
    reader = easyocr.Reader(['en'])
    results = reader.readtext(image)
    extracted_text = [result[1] for result in results]
    return extracted_text

def extract_and_categorize_text(extracted_text):
    card_info = ' '.join(extracted_text)
    
    ph_pattern = r"\+*\d{2,3}-\d{3}-\d{4}"
    mail_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,3}\b"
    url_pattern = r"www\.[A-Za-z0-9]+\.[A-Za-z]{2,3}"
    pin_pattern = r'\d+'
    fax_pattern = r"(Fax\s*:\s*)?\+?\d{2,3}-\d{3}-\d{4}"

    phone = ' '.join(re.findall(ph_pattern, card_info))
    fax = ' '.join(re.findall(fax_pattern, card_info))
    email = ' '.join(re.findall(mail_pattern, card_info))
    website = ' '.join(re.findall(url_pattern, card_info))
    pincode = ' '.join([p for p in re.findall(pin_pattern, card_info) if len(p) == 6])

    name, company = extracted_text[0], extracted_text[2]
    
    return name, phone, fax, email, company, website, pincode


def categorize_and_store_in_firebase(user_id, name, phone, fax, email, company, website, pincode):
    ref = db.reference(f'users/{user_id}/business_cards')
    
    card_data = {
        "name": name,
        "phone": phone,
        "fax": fax,
        "email": email,
        "company": company,
        "website": website,
        "pincode": pincode
    }

    ref.push(card_data)
    st.success("Data stored in Database successfully!")


def create_or_update_google_sheet(user_email, name, phone, fax, email, company, website, pincode):
    try:
        sheet_name = "Business_Cards_details"
        try:
            sheet = client.open(sheet_name)
        except gspread.SpreadsheetNotFound:
            sheet = client.create(sheet_name)
        
        worksheet = sheet.sheet1
        
        if worksheet.row_count == 1:
            worksheet.append_row(['Name', 'Phone', 'Fax', 'Email', 'Company', 'Website', 'Pincode'])
        
        worksheet.append_row([name, phone, fax, email, company, website, pincode])

        sheet.share(user_email, perm_type='user', role='reader')

        sheet_url = sheet.url
        return sheet_url

    except Exception as e:
        st.error(f"Error updating Google Sheet: {e}")
        return None


def business_card_app():
    st.markdown("<h1 style='text-align: center; color:Indigo;'>Bluechip Tech Asia : Extracting Business Card Data</h1>", unsafe_allow_html=True)

    selected = option_menu(None, ["Home", "Upload & Extract"],
                           icons=["house", "cloud-upload"],
                           default_index=0,
                           orientation="horizontal")

    if selected == 'Home':
        st.markdown("### Welcome to the Business Card Application!")

    if selected == 'Upload & Extract':
        file_col, text_col = st.columns([3, 2.5])
        with file_col:
            uploaded_file = st.file_uploader("Choose an image of a business card", type=["jpg", "jpeg", "png"])
            if uploaded_file is not None:
                file_bytes = uploaded_file.read()
                nparr = np.frombuffer(file_bytes, np.uint8)
                image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                st.image(image, channels='BGR', use_column_width=True)

                with st.spinner('Classifying orientation...'):
                    orientation = predict_image_orientation(image)
                    #st.write(f"Predicted orientation: {orientation}")

                    if orientation == 'not_straight':
                        image = rotate_image_if_needed(image, orientation)
                        st.image(image, channels='BGR', use_column_width=True)
                        #st.success("Image rotated successfully.")
                        
            if st.button('Proceed to Extract'):
                with st.spinner('Extracting text...'):
                    extracted_text = extract_text_from_image(image)
                    name, phone, fax, email, company, website, pincode = extract_and_categorize_text(extracted_text)
                    
                    st.write(f"Name: {name}")
                    st.write(f"Phone: {phone}")
                    st.write(f"Fax: {fax}")
                    st.write(f"Email: {email}")
                    st.write(f"Company: {company}")
                    st.write(f"Website: {website}")
                    st.write(f"Pincode: {pincode}")

                    categorize_and_store_in_firebase(st.session_state['user']['localId'], name, phone, fax, email, company, website, pincode)

                    user_email = st.session_state['user']['email']
                    sheet_url = create_or_update_google_sheet(user_email, name, phone, fax, email, company, website, pincode)
                    
                    if sheet_url:
                        st.write(f"View the extracted details in the [Google Sheet]({sheet_url}).")


def login_screen():
    st.title("Login to the App")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        login(email, password)

    if st.button("Sign Up"):
        signup(email, password)


if 'user' not in st.session_state:
    login_screen()
else:
    st.title(f"Welcome, {st.session_state['user']['email']}")
    if st.button("Logout"):
        logout()
    business_card_app()
