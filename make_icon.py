# make_icon.py
from PIL import Image
png_path = "app/resources/logo.png"
ico_path = "app/resources/logo.ico"
img = Image.open(png_path).convert("RGBA")
sizes = [(256,256),(128,128),(64,64),(48,48),(32,32),(24,24),(16,16)]
img.save(ico_path, sizes=sizes)
print("ICO oluşturuldu:", ico_path)
