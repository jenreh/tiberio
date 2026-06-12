# Datenschutzerklärung – Tiberio Heimsteuerung

**Stand:** Juni 2026

Tiberio Heimsteuerung ("der Skill") ist ein privater Smart-Home-Skill für einen
einzelnen Haushalt. Der Skill steuert Geräte (Fernseher, Rollos,
Heizungsthermostate) über einen vom Betreiber selbst betriebenen Heimserver. Er
ist nicht für die öffentliche Zertifizierung oder Verbreitung vorgesehen.

## Verantwortlicher

Jens Rehpöhler
Kontakt: spotnik08@gmail.com

## Welche Daten verarbeitet werden

- **Anmeldedaten (Account Linking):** Beim Verknüpfen des Skills meldest du dich
  über OAuth 2.0 (Authorization Code mit PKCE) am Heimserver an. Dabei werden ein
  Benutzername und ein als kryptografischer Hash gespeichertes Passwort verwendet.
  Das Klartext-Passwort wird zu keinem Zeitpunkt gespeichert.
- **OAuth-Tokens:** Zur Aufrechterhaltung der Verknüpfung werden Access- und
  Refresh-Tokens ausgestellt und auf dem Heimserver gespeichert.
- **Steuerbefehle:** Sprachbefehle werden von Amazon Alexa als Smart-Home-
  Directives an den Heimserver weitergeleitet, dort ausgeführt und nicht dauerhaft
  inhaltlich gespeichert.

## Wo die Daten verarbeitet werden

Sämtliche personenbezogenen Daten werden ausschließlich auf dem vom Betreiber
selbst betriebenen Heimserver verarbeitet und gespeichert. Die in AWS betriebenen
Lambda-Funktionen dienen nur als transparenter Weiterleitungs-Proxy zwischen Alexa
und dem Heimserver; sie speichern keine Inhalte dauerhaft.

## Weitergabe an Dritte

Es findet **keine** Weitergabe, kein Verkauf und keine Vermarktung
personenbezogener Daten an Dritte statt. Es wird keine Werbung ausgeliefert.

## Speicherdauer

Anmeldedaten und Tokens werden gespeichert, solange die Account-Verknüpfung
besteht. Beim Aufheben der Verknüpfung bzw. beim Löschen des Benutzerkontos auf
dem Heimserver werden die zugehörigen Daten entfernt.

## Deine Rechte

Du kannst jederzeit Auskunft über die gespeicherten Daten verlangen sowie deren
Löschung beantragen. Wende dich dazu an die oben genannte Kontaktadresse. Die
Account-Verknüpfung lässt sich zudem jederzeit in der Alexa-App aufheben.

## Kontakt

Bei Fragen zum Datenschutz: spotnik08@gmail.com
