import json

class serializeToJson(obj):
	def toJson(obj):
		def serialize(obj):
			#recursively walk objects hierarchy
			if isinstance(obj, (bool, int, long, float, basestring)):
				return obj
			elif isinstance(obj, dict):
				obj = obj.copy()
				for key in obj:
					obj[key] = serialize(obj[key])
				return obj
			elif isinstance(obj, list):
				return [serialize(item) for item in obj]
			elif isinstance(obj, tuple):
				return tuple(serialize([item for item in obj]))
			elif hasattr(obj, '__dict__'):
				return serialize(obj.__dict__)
			else:
				return repr(obj) #don't know how to handle, convert to string
		return json.dumps(serialize(obj))

