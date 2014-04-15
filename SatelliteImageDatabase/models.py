from mongoengine import *
from datetime import datetime

class Image(Document):
	name = StringField(max_length=255)
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

class ImageBand(Document):
	rasterData = ReferenceField(ImageTileRaster)
	xResolution = FloatField()
	yResolution = FloatField()

class ImageTile(Document):
	polygonBorder = PolygonField()
	xSize = IntField()
	ySize = IntField()

	indexTileX = IntField()
	indexTileY = IntField()

	image = ReferenceField(Image)

	band1 = ReferenceField(ImageBand)
	band2 = ReferenceField(ImageBand)
	band3 = ReferenceField(ImageBand)
	band4 = ReferenceField(ImageBand)
	band5 = ReferenceField(ImageBand)
	band6 = ReferenceField(ImageBand)
	band7 = ReferenceField(ImageBand)
	band8 = ReferenceField(ImageBand)
	band9 = ReferenceField(ImageBand)
	band10 = ReferenceField(ImageBand)
	band11 = ReferenceField(ImageBand)

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
	tileMatrix = ListField(ReferenceField(ImageTile))

	created = DateTimeField(default=datetime.now)

	# meta = {
 #        'indexes': [
 #            {'fields': ['created'], 'expireAfterSeconds': 300}
 #        ]
 #    }