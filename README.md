Folgende Pakete müssen installiert werden: 

kivy	
pandas
numpy	
opencv-contrib-python
sounddevice


pip install kivy pandas numpy opencv-contrib-python sounddevice

## Ereignis-Logging

Die Tabletop-App vergibt für jedes UI-Ereignis eine eindeutige `event_id` sowie
einen hochauflösenden Zeitstempel (`t_local_ns`) auf Basis von
`time.perf_counter_ns()`. Alle Ereignisse werden lokal im jeweiligen
Session-Log (`logs/events_<session>.sqlite3`) und in den CSV-Rundendateien
gespeichert. Die frühere Eye-Tracking-Integration wurde komplett entfernt.
