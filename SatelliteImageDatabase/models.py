from mongoengine import *
from datetime import datetime

class Image(Document):
	name = StringField(max_length=255, unique=True)
	date = DateTimeField()
	# bands = ListField(ReferenceField(ImageBand))

	wkt = StringField()

	meta = {
		'indexes': [
			[('date', 1)]
		]
	}

class ImageTileRaster(Document):
	raster = BinaryField()	

class ImageTile(Document):
	polygonBorder = PolygonField()
	xSize = IntField()
	ySize = IntField()

	indexTileX = IntField()
	indexTileY = IntField()

	image = ReferenceField(Image)

	band1 = ReferenceField(ImageTileRaster)
	band2 = ReferenceField(ImageTileRaster)
	band3 = ReferenceField(ImageTileRaster)
	band4 = ReferenceField(ImageTileRaster)
	band5 = ReferenceField(ImageTileRaster)
	band6 = ReferenceField(ImageTileRaster)
	band7 = ReferenceField(ImageTileRaster)
	band8 = ReferenceField(ImageTileRaster)
	band9 = ReferenceField(ImageTileRaster)
	band10 = ReferenceField(ImageTileRaster)
	band11 = ReferenceField(ImageTileRaster)

	def getXSize(self, band):
		if band == 8:
			return self.xSize*2
		return self.xSize

	def getYSize(self, band):
		if band == 8:
			return self.ySize*2
		return self.ySize

	meta = {
		'indexes': [
			[('indexTileX', 1), ('indexTileY', 1)]
		]
	}

class QueryResult(Document):
	imageName = StringField(max_length=255)
	inputPolygons = ListField(PolygonField())
	tileMatrix = ListField(ReferenceField(ImageTile))

	created = DateTimeField(default=datetime.now)

	# meta = {
 #        'indexes': [
 #            {'fields': ['created'], 'expireAfterSeconds': 300}
 #        ]
 #    }