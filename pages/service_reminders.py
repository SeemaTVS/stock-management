import datetime
from datetime import timedelta
import pandas as pd
import requests
import streamlit as st

st.title("TVS Agency Service Reminder Portal")

# Google Sheet and Web App endpoints
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1Y4yyok1dtw0RZyhc46vwHZ4frW9SyTsHCXMBSpegWlM/edit?gid=0#gid=0"
WEB_APP_URL = "https://script.google.com/macros/s/AKfycbymkbPavkWPw_5kFEN7S6KQTg2MvS_zqAmGXXkqBAjVDo7XrnUCj9GKKKrA_heBvWZvmQ/exec"


def get_csv_export_url(sheet_url, sheet_name="Service_Reminders"):
  import re

  match = re.search(r"/d/([a-zA-Z0-9-_]+)", sheet_url)
  if match:
    return (
        f"https://docs.google.com/spreadsheets/d/{match.group(1)}/gviz/tq?"
        f"tqx=out:csv&sheet={sheet_name}"
    )
  return sheet_url


EXPECTED_COLS = [
    "Name",
    "Phone",
    "Bike",
    "Free_Services_Count",
    "Latest_Service_Date",
    "Current_Service_Stage",
    "Next_Due_Date",
    "Status",
]


@st.cache_data(ttl=10)
def load_data():
  try:
    csv_url = get_csv_export_url(GOOGLE_SHEET_URL, "Service_Reminders")
    df_loaded = pd.read_csv(csv_url)
    for col in EXPECTED_COLS:
      if col not in df_loaded.columns:
        df_loaded[col] = ""
    return df_loaded
  except Exception as e:
    st.warning(
        "Could not load Service_Reminders tab from Google Sheet yet. Details:"
        f" {e}"
    )
    return pd.DataFrame(columns=EXPECTED_COLS)


def save_data_to_cloud(df_to_save):
  try:
    if WEB_APP_URL:
      records = df_to_save[EXPECTED_COLS].to_dict(orient="records")
      payload = {"type": "service_reminders", "data": records}
      response = requests.post(WEB_APP_URL, json=payload, timeout=10)
      if response.status_code == 200:
        st.success("Changes synced to Google Sheets!")
      else:
        st.error(f"Sync failed with status code: {response.status_code}")
  except Exception as e:
    st.error(f"Error syncing to cloud: {e}")


df = load_data()

# Sidebar for management (Adding / Editing)
st.sidebar.header("Customer Management")
action_choice = st.sidebar.radio("Actions", ["View Reminders", "Add Customer", "All Records"])

if action_choice == "Add Customer":
  st.sidebar.subheader("Register New Vehicle")
  with st.sidebar.form("add_customer_form"):
    name = st.text_input("Customer Name")
    phone = st.text_input("Phone Number")
    bike = st.text_input("Bike Model")
    purchase_date = st.date_input("Purchase Date", datetime.date.today())
    free_services_count = st.selectbox("Free Services Scheme", [3, 4], format_func=lambda x: f"{x} Free Services")
    
    submitted = st.form_submit_button("Save Customer")
    if submitted:
      if name and phone:
        next_due = purchase_date + timedelta(days=60)
        stage = "1st Service (Free)"
        
        new_row = pd.DataFrame([{
            "Name": name.strip(),
            "Phone": str(phone).strip(),
            "Bike": bike.strip(),
            "Free_Services_Count": int(free_services_count),
            "Latest_Service_Date": str(purchase_date),
            "Current_Service_Stage": stage,
            "Next_Due_Date": str(next_due),
            "Status": "Pending"
        }])
        
        updated_df = pd.concat([df, new_row], ignore_index=True)
        save_data_to_cloud(updated_df)
        st.success(f"Customer {name} added successfully!")
        st.rerun()
      else:
        st.error("Please enter Name and Phone.")

elif action_choice == "All Records":
  st.subheader("Complete Customer Service Database")
  if not df.empty:
    st.dataframe(df, use_container_width=True)
  else:
    st.info("No records found.")

else:
  st.subheader("Service Calls Due & Overdue")
  if not df.empty and "Next_Due_Date" in df.columns:
    today = str(datetime.date.today())
    due_filter = (df["Next_Due_Date"] <= today) & (df["Status"] == "Pending")
    due_df = df[due_filter]

    if not due_df.empty:
      st.write(f"You have **{len(due_df)}** customer calls pending action:")
      for index, row in due_df.iterrows():
        with st.expander(f"{row['Name']} - {row['Bike']} | Due: {row['Next_Due_Date']}"):
          st.write(f"**Phone:** {row['Phone']}")
          st.write(f"**Upcoming Milestone:** {row['Current_Service_Stage']}")
          st.write(f"**Latest Date on Record:** {row['Latest_Service_Date']}")

          col1, col2, col3 = st.columns(3)
          
          with col1:
            # Direct phone dialer link
            st.markdown(f'<a href="tel:{row["Phone"]}" target="_self"><button style="width:100%;background-color:#4CAF50;color:white;border:none;padding:8px;border-radius:4px;cursor:pointer;">📞 Call Now</button></a>', unsafe_allow_html=True)

          with col2:
            whatsapp_link = f"https://wa.me/91{row['Phone']}?text=Hello%20{row['Name']},%20this%20is%20from%20SEEMA%20TVS.%20Your%20{row['Bike']}%20is%20due%20for%20{row['Current_Service_Stage']}."
            st.markdown(f'<a href="{whatsapp_link}" target="_blank"><button style="width:100%;background-color:#25D366;color:white;border:none;padding:8px;border-radius:4px;cursor:pointer;">💬 WhatsApp</button></a>', unsafe_allow_html=True)

          with col3:
            if st.button("Mark Completed", key=f"complete_{index}"):
              current_stage = str(row["Current_Service_Stage"])
              free_limit = int(row["Free_Services_Count"])
              base_date = datetime.date.today()

              next_stage = current_stage
              next_due_calc = base_date + timedelta(days=180)

              if free_limit == 4:
                if "1st" in current_stage:
                  next_stage = "2nd Service (Free)"
                  next_due_calc = base_date + timedelta(days=120)
                elif "2nd" in current_stage:
                  next_stage = "3rd Service (Free)"
                  next_due_calc = base_date + timedelta(days=240)
                elif "3rd" in current_stage:
                  next_stage = "4th Service (Free)"
                  next_due_calc = base_date + timedelta(days=365)
                else:
                  next_stage = "Subsequent Service (Paid)"
                  next_due_calc = base_date + timedelta(days=90)
              else:
                if "1st" in current_stage:
                  next_stage = "2nd Service (Free)"
                  next_due_calc = base_date + timedelta(days=180)
                elif "2nd" in current_stage:
                  next_stage = "3rd Service (Free)"
                  next_due_calc = base_date + timedelta(days=365)
                elif "3rd" in current_stage:
                  next_stage = "4th Service (Paid)"
                  next_due_calc = base_date + timedelta(days=548)
                else:
                  next_stage = "Subsequent Service (Paid)"
                  next_due_calc = base_date + timedelta(days=180)

              df.loc[index, "Current_Service_Stage"] = next_stage
              df.loc[index, "Latest_Service_Date"] = str(base_date)
              df.loc[index, "Next_Due_Date"] = str(next_due_calc)
              df.loc[index, "Status"] = "Pending"

              save_data_to_cloud(df)
              st.success(f"Updated! Next service scheduled for {next_due_calc}.")
              st.rerun()
    else:
      st.info("No service calls due right now.")
  else:
    st.info("No customer records found.")
