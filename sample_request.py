import requests

url = "https://8000-jatindotpy-fastscraper-m7ov7l272zr.ws-us118.gitpod.io/scrape"
urls=  {"urls": ["https://console.groq.com/docs/speech-to-text", "https://cloud.google.com/speech-to-text", "https://cloud.google.com/speech-to-text/docs/release-notes"]}
response = requests.post(url, json=urls)

print(response.text)


