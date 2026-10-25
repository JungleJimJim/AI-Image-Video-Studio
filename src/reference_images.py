"""Validate optional native reference conditioning without treating frames as references."""
def validate_ids(raw,field,maximum):
    values=raw.get(field,[])
    if not isinstance(values,list) or any(not isinstance(x,str) or not x or len(x)>100 for x in values):
        raise ValueError('Choose valid reference images from Library or local files.')
    if values and not maximum:raise ValueError('The selected model does not support extra reference images in this workflow.')
    if len(values)>maximum:raise ValueError(f'Use up to {maximum} reference images with this model.')
    if len(values)!=len(set(values)):raise ValueError('Choose different reference images.')
    return list(values)
