def export_image(image, description, folder, aoi, scale=30):

    task = ee.batch.Export.image.toDrive(
        image=image.clip(aoi),
        description=description,
        folder=folder,
        scale=scale,
        region=aoi.geometry().bounds().getInfo()['coordinates'],
        crs='EPSG:26914',
        maxPixels=1e13
    )
    task.start()
    print(f"Export task started: {description}")


def export_summary_csv(