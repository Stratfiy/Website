# OrderShed website

Static marketing site for OrderShed, the parts business of NAutomation Labs Private Limited.

- No build step. Vercel settings: Framework preset "Other", no build command, output directory `.`
- `index.html` is the whole site; `thanks.html` is shown after a quote request.
- The quote form posts to FormSubmit and emails office@nautomationlabs.com. It only sends when the hostname contains "ordershed".
- Video clips are stock footage from Pexels, graded black and white.
