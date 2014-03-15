from mongoengine import *

class Image(Document):
	name = StringField(max_length=255)
	date = DateTimeField()
	# bands = ListField(ReferenceField(ImageBand))

class ImageTileRaster(Document):
	raster = BinaryField()	

class ImageBand(Document):
	bandNumber = IntField()
	# tiles = ListField(ReferenceField(ImageTile))

	image = ReferenceField(Image)

class ImageTile(Document):
	polygonBorder = PolygonField()
	tileRaster = ReferenceField(ImageTileRaster)
	xSize = IntField()
	ySize = IntField()

	indexTileX = IntField()
	indexTileY = IntField()

	band = ReferenceField(ImageBand)	

class QueryResult(Document):
	imageName = StringField(max_length=255)
	imageBand = IntField()
	tileMatrix = ListField(ReferenceField(ImageTile))