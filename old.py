import streamlit as st
import pymongo
from datetime import datetime
import pytz
import re
from twilio.rest import Client
import os

# Twilio configuration
twilio_account_sid = os.getenv("ACCOUNT_SID")
twilio_auth_token = os.getenv("ACCOUNT_AUTH")
twilio_sender_phone_number = os.getenv("ACCOUNT_NUMBER")
twilio_client = Client(twilio_account_sid, twilio_auth_token)

# MongoDB connection URI
client = pymongo.MongoClient("mongodb+srv://ishansheth31:Kevi5han1234@breezytest1.saw2kxe.mongodb.net/")

# Select your database
db = client["primecareofga"]

# Select your collections
appointments_collection = db["appointments"]
patients_collection = db["patients"]
reports_collection = db["reports"]

# Get the current time in EST
est = pytz.timezone('US/Eastern')
current_time = datetime.now(est)

# Helper function to format the date (without leading zeros for day and hour)
def format_date(iso_date_str):
    dt = datetime.fromisoformat(iso_date_str.replace("Z", "+00:00"))
    day = dt.strftime("%d").lstrip("0")  # Remove leading zero from day
    hour = dt.strftime("%I").lstrip("0")  # Remove leading zero from hour
    return dt.strftime(f"%B {day}, %Y at {hour}:%M%p")

# Helper function to format phone number (xxx-xxx-xxxx)
def format_phone_number(phone):
    phone_digits = re.sub(r'\D', '', phone)  # Remove non-numeric characters
    return f"{phone_digits[:3]}-{phone_digits[3:6]}-{phone_digits[6:]}"

# Helper function to determine if an appointment is upcoming or past
def get_appointment_status(appointment_date_str):
    utc_appointment_date = datetime.fromisoformat(appointment_date_str)
    st.write(utc_appointment_date)
    current_time_utc = datetime.now()
    if utc_appointment_date > current_time_utc:
        return "Upcoming", "green"
    else:
        return "Past", "red"

# Helper function to get upload status from reports
def get_upload_status(patient_uuid):
    report = reports_collection.find_one({"patient_uuid": patient_uuid})
    if report:
        return "Complete" if report["upload_status"] == "complete" else "Incomplete"
    else:
        return "Incomplete"

# Twilio message builder
def string_builder(patient_name, date, link):
    return (f"Hi {patient_name}, this is PrimeCare of Georgia. Your appointment is coming up soon. "
            f"Please click the blue highlighted link below to fill out a mandatory 5-minute form before your visit.\n"
            f"{link}")

# Function to send message using Twilio
def send_message(phone_number, patient_name, date, appointment_uuid):
    link = f"https://wonderful-beach-0bf67b61e.5.azurestaticapps.net/{appointment_uuid}"
    final_string = string_builder(patient_name=patient_name, date=date, link=link)
    try:
        message = twilio_client.messages.create(
            from_=twilio_sender_phone_number,
            body=final_string,
            to=phone_number
        )
        return {
            "message_sid": message.sid,
            "status": message.status,
            "date_sent": message.date_sent,
        }
    except Exception as e:
        st.error(f"Message couldn't send: {str(e)}")
        return None

# Function to increment the test message counter in the database
def increment_test_message_counter(appointment_id):
    appointments_collection.update_one(
        {"_id": appointment_id},
        {"$inc": {"test_message_counter": 1}}
    )

# Title
st.title("Breezy Medical Dashboard")

# Sidebar - Add Home Button above search
if st.sidebar.button("🏠 Home"):
    selected_patient_id = None

# Sidebar - Searchable dropdown for patients
st.sidebar.title("Search Patient")
all_patients = list(patients_collection.find({}, {"first_name": 1, "last_name": 1, "id": 1, "_id": 0}))
patient_options = [f"{patient['first_name']} {patient['last_name']}" for patient in all_patients]
patient_data = {f"{patient['first_name']} {patient['last_name']}": patient['id'] for patient in all_patients}
selected_patient_name = st.sidebar.selectbox("Select a Patient", options=patient_options)
selected_patient_id = patient_data.get(selected_patient_name)

# Fetch 10 most recent upcoming appointments after the current time (EST)
upcoming_appointments = appointments_collection.find({
    "scheduled_date": {"$gt": current_time.isoformat()},
}).sort("scheduled_date", pymongo.ASCENDING).limit(10)

# Sidebar - List of Upcoming Patients
st.sidebar.title("Upcoming Patients")
for appointment in upcoming_appointments:
    patient_id = appointment["patient"]
    patient = patients_collection.find_one({"id": patient_id}, {"first_name": 1, "last_name": 1, "_id": 0})
    patient_name = f"{patient['first_name']} {patient['last_name']}"
    formatted_date = format_date(appointment['scheduled_date'])
    if st.sidebar.button(f"{patient_name} - {formatted_date}"):
        selected_patient_id = patient_id

# If a patient is selected, fetch and display their detailed information
if selected_patient_id:
    patient_info = patients_collection.find_one({"id": selected_patient_id}, {"first_name": 1, "last_name": 1, "phones": 1, "_id": 0})
    if patient_info.get('phones') and len(patient_info['phones']) > 0:
        formatted_phone = format_phone_number(patient_info['phones'][0]['phone'])
        phone_link = f"tel:{formatted_phone.replace('-', '')}"
        st.markdown(f"**Phone Number:** [📞 {formatted_phone}]({phone_link})")
    else:
        st.markdown("**Phone Number:** Not available")

    st.header(f"Details for {patient_info['first_name']} {patient_info['last_name']}")

    # Fetch their most recent appointment
    recent_appointment = appointments_collection.find_one({"patient": selected_patient_id}, sort=[("scheduled_date", pymongo.DESCENDING)])
    if recent_appointment:
        formatted_date = format_date(recent_appointment['scheduled_date'])
        appointment_status, status_color = get_appointment_status(recent_appointment['scheduled_date'])
        
        # Get the counters and total messages sent
        original_counter = recent_appointment.get("counter", 5)
        test_message_counter = recent_appointment.get("test_message_counter", 0)
        total_messages_sent = 6 - original_counter + test_message_counter

        upload_status = get_upload_status(recent_appointment.get("uuid", ""))

        # Display appointment details
        st.markdown(f"**Appointment Date:** {formatted_date}")
        st.markdown(f"**Appointment Stage:** :{status_color}[{appointment_status}]")
        st.markdown(f"**Appointment Type:** {recent_appointment['reason']}")
        st.markdown(f"**Messages Sent:** {total_messages_sent}")
        st.markdown(f"**Assessment Status:** {upload_status}")

        # Send follow-up text button
        if appointment_status == "Upcoming":
            if st.button(f"Send Follow-Up Text to {patient_info['first_name']}"):
                patient_phone_number = patient_info['phones'][0]['phone'] if patient_info.get('phones') else None
                if patient_phone_number:
                    formatted_phone_number = f"+1{re.sub(r'[^0-9]', '', patient_phone_number)}"
                    result = send_message(
                        phone_number=formatted_phone_number,
                        patient_name=patient_info['first_name'],
                        date=formatted_date,
                        appointment_uuid=recent_appointment["uuid"]
                    )
                    if result:
                        # Increment the test message counter in the database
                        increment_test_message_counter(recent_appointment["_id"])
                        st.success(f"Follow-up text sent to {patient_info['first_name']}! (Message SID: {result['message_sid']})")
                else:
                    st.error(f"No valid phone number found for {patient_info['first_name']}.")
else:
    st.write("No patient selected. Use the search or click on an upcoming patient.")
