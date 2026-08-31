"""Smoke test adaptateurs AvisBoost — mode test = journalisation réelle, aucun envoi."""
import adapters.whatsapp_adapter as wa
import adapters.sms_adapter as sa
import adapters.google_reviews_adapter as ga
import adapters.ia_reviews as ia

r1 = wa.send_whatsapp("+33612345678", "Bonjour Julie 👋 merci pour votre visite chez Salon Lumière !")
print("WHATSAPP:", r1["mode"], "| ok", r1["ok"])

r2 = sa.send_sms("+33612345678",
                 "Bonjour Julie, votre avis Google nous aide : https://search.google.com/local/writereview?placeid=abc")
print("SMS:", r2["mode"], "| ok", r2["ok"])

r3 = ga.fetch_reviews(location_id="123")
print("GOOGLE:", r3["mode"], "| ok", r3["ok"])

r4 = ia.generate_reply("Très bon accueil, je reviendrai !", "Salon Lumière", 5)
print("IA reply:", r4["mode"], "| ok", r4["ok"])
print("REPLY:", r4["reponse"])
