# TridentChat

A mobile-first email client prototype that uses phone numbers as addresses (`9876543210@phonemail.com`) and presents the inbox as conversations. It includes dark mode and adjustable magnification in account settings.

Messages use a unique ID and per-account mailbox state. Only the sender and registered recipients can retrieve a message, and moving a message between Inbox, Spam, and Trash changes only that account's mailbox. Drafts are also scoped to their owner.

## Run it

Install Docker Desktop, then run:

```sh
docker compose up -d --build
```

Open [http://localhost:8080](http://localhost:8080). Create an account with a phone number and password, then confirm ownership of the number by SMS or automated call. A starter inbox is included so you can explore the app immediately. Account and mailbox data persists in the `phonemail-data` Docker volume.

## In the demo

- Responsive WhatsApp-inspired onboarding and chat inbox; search; All, Unread, Attachments, and Favorites filters.
- Conversation replies, subject handling, group composition, favorites, account settings, and alias addresses.
- Password-based account creation followed by Twilio SMS or automated-call phone verification; password login remains available after verification.
- Persistent local API and JSON data volume. This is a hackathon MVP: mail is stored locally in the service, and outbound email delivery, inbound mail routing, IVR, OTP/SMS gateway hooks, and real push notifications need provider configuration / integration before production.

## Optional Twilio trial SMS and inbound mail hook

Add `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, and a long random `INBOUND_WEBHOOK_TOKEN` to a local `.env` file, then restart the service. Twilio trial restrictions apply: recipients generally need to be verified in the Twilio console. When an email is routed to a TridentChat user without the app, TridentChat sends the requested sender/subject text notice.

An email gateway can deliver received mail by POSTing JSON to `/api/inbound` with `X-Webhook-Token` set to the configured token and `to`, `from`, `subject`, and `body` fields. This stores the mail and triggers an SMS for users without the app. An email provider and public webhook URL must be configured separately. Twilio SMS notices are implemented; account creation through toll-free IVR/SMS still requires wiring a purchased/configured Twilio number and webhook flow. Never commit live credentials.
# Twilio SMS and voice verification

Password signup saves the account first, then requires phone ownership confirmation by text message or automated call before opening the inbox. In a Twilio trial, use **Identity → Verify → Overview → Try out Verify**; verify the test recipient there and copy the real Verify Service SID shown in its API example. A purchased Twilio number is not needed for Verify. Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_VERIFY_SERVICE_SID` in a local `.env`. Do not commit `.env` or share its credentials. `TWILIO_FROM_NUMBER` is used for separate new-email SMS notifications.

Phone numbers with 10 digits are treated as Indian numbers (`+91`). For other countries, enter the full number beginning with `+` and country code.

## Account persistence

New accounts are saved to `/data/phonemail.json` on the named `phonemail-data` volume before phone verification begins. Closing the browser or stopping the container does not remove them; `docker compose down` also preserves the volume. Avoid `docker compose down -v`, which deletes the volume and its accounts. The included Excel workbook is a separate tracking template, not the app's live account database.
