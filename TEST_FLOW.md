
# Replace these if needed
ENDPOINT="https://8bb39f63-040b-40f4-b84d-dde3e0ee9d98-00-3ao8sa8hbqym4.riker.replit.dev/webhook/whatsapp?debug=1"
FROM_PHONE="whatsapp:+919152635928"
TO_PHONE="whatsapp:+14155238886"

```
# Helper function
send() {
  printf "\n--- $1 ---\n"
  shift
  curl -s -X POST "$ENDPOINT" \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    -d "From=$FROM_PHONE" \
    -d "To=$TO_PHONE" \
    "$@" \
    | jq .
}

# 1) Basic text ping (sanity)
send "Ping (basic)" -d "Body=Hello debug" -d "MessageSid=SM_TEST_DEBUG_001" -d "NumMedia=0"

# -----------------------
# Onboarding flows (simulate a fresh user)
# -----------------------
# 2a) Start onboarding - send any message from a fresh number (creates user and should ask name)
send "Start onboarding (auto-create user)" -d "Body=Hi" -d "MessageSid=SM_ONBOARD_START_001"

# 2b) Reply with name (text)
# Use the same From but new SID - this simulates the user's reply to the name prompt
send "Onboarding - reply with name (Alice)" -d "Body=Alice" -d "MessageSid=SM_ONBOARD_NAME_002"

# 2c) Diet preference - numeric reply (1=Veg,2=Non-Veg,3=Both)
send "Onboarding - diet (numeric '1' => veg)" -d "Body=1" -d "MessageSid=SM_ONBOARD_DIET_003"

# 2d) Cuisine preference - text reply (e.g., South Indian)
send "Onboarding - cuisine (text 'South Indian')" -d "Body=South Indian" -d "MessageSid=SM_ONBOARD_CUISINE_004"

# 2e) Allergies - text or numeric list (e.g., '2,4' or 'peanut')
# According to your mapping 2=dairy,4=peanut
send "Onboarding - allergies (numeric '2,4')" -d "Body=2,4" -d "MessageSid=SM_ONBOARD_ALLERGY_005"

# 2f) Household - numeric (1..5)
send "Onboarding - household ('3' small family)" -d "Body=3" -d "MessageSid=SM_ONBOARD_HOUSE_006"

# 2g) Alternative: user replies 'skip' for name
send "Onboarding - skip name -> Guest" -d "Body=skip" -d "MessageSid=SM_ONBOARD_SKIP_007"

# -----------------------
# Media flows (images, multiple media)
# -----------------------
# 3a) Send image URL (single). The webhook will set type=image and ImageService will try detection.
# Use a real, publicly-accessible image URL (example uses Wikimedia sample). Replace if you prefer.
IMG_URL="https://upload.wikimedia.org/wikipedia/commons/4/41/Simple_salad.jpg"
send "Media - image (single)" -d "Body=Here is a photo" -d "MessageSid=SM_MEDIA_IMG_101" -d "NumMedia=1" -d "MediaUrl0=$IMG_URL"

# 3b) Send image without text (tests path where text is None)
send "Media - image (no text)" -d "Body=" -d "MessageSid=SM_MEDIA_IMG_102" -d "NumMedia=1" -d "MediaUrl0=$IMG_URL"

# 3c) Send multiple media (two images)
IMG2="https://upload.wikimedia.org/wikipedia/commons/7/76/Vegetable_platter.jpg"
send "Media - multiple images" -d "Body=Two images" -d "MessageSid=SM_MEDIA_MULTI_103" -d "NumMedia=2" -d "MediaUrl0=$IMG_URL" -d "MediaUrl1=$IMG2"

# 3d) Send non-image media (audio/video) - webhook will set media type
VIDEO_URL="https://www.learningcontainer.com/wp-content/uploads/2020/05/sample-mp4-file.mp4"
send "Media - video" -d "Body=Video test" -d "MessageSid=SM_MEDIA_VIDEO_104" -d "NumMedia=1" -d "MediaUrl0=$VIDEO_URL"

# -----------------------
# Pantry / Ingredient flows
# -----------------------
# 4a) Pantry: text listing ingredients (Hinglish or English)
send "Pantry - I have potatoes and tomatoes" -d "Body=I have potatoes and tomatoes" -d "MessageSid=SM_PANTRY_201"

# 4b) Pantry - phrased request
send "Pantry - what can i make with potatoes?" -d "Body=What can I make with potatoes and onions?" -d "MessageSid=SM_PANTRY_202"

# -----------------------
# Recipe flows (specific)
# -----------------------
# 5a) Recipe: "recipe for ..."
send "Recipe - specific ('recipe for chole')" -d "Body=Recipe for chole" -d "MessageSid=SM_RECIPE_301"

# 5b) Recipe: How to make phrasing
send "Recipe - how to make dal" -d "Body=How to make dal?" -d "MessageSid=SM_RECIPE_302"

# -----------------------
# Mood / Craving flows
# -----------------------
send "Mood - spicy craving" -d "Body=I am in the mood for something spicy" -d "MessageSid=SM_MOOD_401"
send "Mood - comfort food (cream/rich)" -d "Body=Feeling like comfort food" -d "MessageSid=SM_MOOD_402"

# -----------------------
# General 'what's for dinner' flows
# -----------------------
send "What should I cook tonight?" -d "Body=What should I cook tonight?" -d "MessageSid=SM_WHATSDINNER_501"
send "Short 'what for dinner' " -d "Body=What for dinner" -d "MessageSid=SM_WHATSDINNER_502"

# -----------------------
# Weekly plan / scheduling
# -----------------------
send "Plan week - weekly meal plan" -d "Body=Plan my week - weekly meal plan" -d "MessageSid=SM_PLANWEEK_601"

# -----------------------
# Duplicate / retry simulation (same MessageSid twice)
# -----------------------
send "Duplicate test - first delivery (should process)" -d "Body=Duplicate test attempt 1" -d "MessageSid=SM_DUPLICATE_TEST"
# Send again with same MessageSid: second should be deduped by DB/in-memory or return already_processed
send "Duplicate test - second delivery (same SID - should short-circuit)" -d "Body=Duplicate test attempt 2" -d "MessageSid=SM_DUPLICATE_TEST"

# -----------------------
# Edge cases & invalid input
# -----------------------
# 1) Empty Body but with MediaUrl
send "Edge - empty body but media present" -d "Body=" -d "MessageSid=SM_EDGE_MEDIA_ONLY" -d "NumMedia=1" -d "MediaUrl0=$IMG_URL"

# 2) Gibberish body (test classifier fallback)
send "Edge - gibberish fallback" -d "Body=asdf qwer zxcv" -d "MessageSid=SM_EDGE_GIBBERISH"

# 3) Long body truncated check
LONG_BODY=$(printf 'x%.0s' {1..2000})
send "Edge - long body (2k chars)" -d "Body=$LONG_BODY" -d "MessageSid=SM_EDGE_LONGBODY"

# -----------------------
# Interactive-like simulation (numbers / 'list' replies)
# -----------------------
# Many WhatsApp interactive replies come as simple text payloads from Twilio; numeric replies below.
send "Interactive simulation - reply option '2'" -d "Body=2" -d "MessageSid=SM_INTERACTIVE_701"

# -----------------------
# Replace From phone or test another user
# -----------------------
# If you want to test a different sender phone, override FROM_PHONE per call:
# (example)
curl -s -X POST "$ENDPOINT" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d "From=whatsapp:+919988776655" \
  -d "To=$TO_PHONE" \
  -d "Body=Hello from different user" \
  -d "MessageSid=SM_OTHERUSER_999" | jq .

echo "Done."
```

## Notes, tips & expected behavior
* All commands hit ?debug=1 so the endpoint returns JSON diagnostics. Inspect diagnostics → incoming_record → process_result to see DB, deduper, and message handler outcomes.
* For onboarding: first message from a phone will auto-create a user. Then follow the numeric/text replies above to step through the flow. The MessageSid must be unique per POST to simulate distinct incoming messages — except in the duplicate test where we intentionally reuse it.
* Media: Twilio will provide MediaUrl0, MediaUrl1, ... for attachments. The ImageService will attempt detection; if Vision is not configured it falls back to canned suggestions. Use real public URLs to see detection work.
* Pantry flow expects ingredient words like potato, tomato, chicken, etc. Your classifier will route these to PANTRY_HELP.
* If you want the webhook to treat a request as interactive type=interactive, you’d have to craft the internal message shape that MessageHandler expects — for most testing the textual replies (numbers, titles) are sufficient because your onboarding handlers look at the text.body or numeric values.
* If you get duplicate/already_processed in diagnostics for repeated SIDs, that’s expected — tests for idempotency succeeded.
* If you see 500 or your webhook returned XML even with ?debug=1, ensure MessageSid is unique (Twilio will retry); check logs, then rerun the specific failing command and paste the returned diagnostics if you want help debugging.
