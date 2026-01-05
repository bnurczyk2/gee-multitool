import ee

def toa(image, satellite):
    sat = str(satellite).upper()

    if sat.startswith('L'):  # Landsat
        
        qa = image.select('QA_PIXEL')
        # Bit 3 is cloud shadow in C2 L2; adjust if you need cloud bit as well
        cloud_shadow = qa.bitwiseAnd(1 << 3).gt(0)
        return image.updateMask(cloud_shadow.Not())
    elif sat == 'S2':
        qa = image.select('QA60')

        cloud_bit_mask  = 1 << 10
        cirrus_bit_mask = 1 << 11
    
        mask = (
            qa.bitwiseAnd(cloud_bit_mask).eq(0)
            .And(qa.bitwiseAnd(cirrus_bit_mask).eq(0))
        )
    
        return image.updateMask(mask).divide(10000)

def sr(image, satellite):
    sat = str(satellite).upper()

    if sat.startswith('L'):  # Landsat
        qa = image.select('QA_PIXEL')
        cloud_shadow = qa.bitwiseAnd(1 << 3).gt(0)
        cloud        = qa.bitwiseAnd(1 << 5).gt(0)  # bit 5 is cloud in C2 L2
        return image.updateMask(cloud_shadow.Or(cloud).Not())

    elif sat == 'S2':  # Sentinel-2 SR has SCL
        scl = image.select('SCL')
        bad = (scl.eq(0)  # No data
               .Or(scl.eq(1))   # Saturated/defective
               .Or(scl.eq(3))   # Cloud shadow
               .Or(scl.eq(8))   # Cloud medium prob
               .Or(scl.eq(9))   # Cloud high prob
               .Or(scl.eq(10))  # Thin cirrus
               .Or(scl.eq(11))) # Snow/ice
        return image.updateMask(bad.Not())

    # Fallback: no masking
    return image