import os
import google.generativeai as genai

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

model = genai.GenerativeModel("gemini-2.5-flash")
resp = model.generate_content("Say hi in one short sentence.")
print(resp.text)
