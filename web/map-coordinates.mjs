const PI = Math.PI;
const A = 6378245.0;
const EE = 0.00669342162296594323;

export function wgs84ToGcj02(position) {
  const [lon, lat, ...rest] = position;
  if (!Number.isFinite(lon) || !Number.isFinite(lat) || outsideChina(lon, lat)) {
    return [...position];
  }

  let deltaLat = transformLat(lon - 105.0, lat - 35.0);
  let deltaLon = transformLon(lon - 105.0, lat - 35.0);
  const radLat = lat / 180.0 * PI;
  let magic = Math.sin(radLat);
  magic = 1 - EE * magic * magic;
  const sqrtMagic = Math.sqrt(magic);
  deltaLat = (deltaLat * 180.0) / (((A * (1 - EE)) / (magic * sqrtMagic)) * PI);
  deltaLon = (deltaLon * 180.0) / ((A / sqrtMagic) * Math.cos(radLat) * PI);
  return [lon + deltaLon, lat + deltaLat, ...rest];
}

export function geojsonWgs84ToGcj02(value) {
  if (!value || typeof value !== "object") return value;
  if (value.type === "FeatureCollection") {
    return { ...value, features: (value.features || []).map(geojsonWgs84ToGcj02) };
  }
  if (value.type === "Feature") {
    return { ...value, geometry: transformGeometry(value.geometry) };
  }
  return transformGeometry(value);
}

function transformGeometry(geometry) {
  if (!geometry || typeof geometry !== "object") return geometry;
  if (geometry.type === "GeometryCollection") {
    return {
      ...geometry,
      geometries: (geometry.geometries || []).map(transformGeometry),
    };
  }
  const depth = ({ Point: 0, MultiPoint: 1, LineString: 1, MultiLineString: 2, Polygon: 2, MultiPolygon: 3 })[geometry.type];
  if (!Number.isInteger(depth)) return { ...geometry };
  return { ...geometry, coordinates: transformCoordinates(geometry.coordinates, depth) };
}

function transformCoordinates(coordinates, depth) {
  if (depth === 0) return wgs84ToGcj02(coordinates);
  return (coordinates || []).map((item) => transformCoordinates(item, depth - 1));
}

function outsideChina(lon, lat) {
  return lon < 72.004 || lon > 137.8347 || lat < 0.8293 || lat > 55.8271;
}

function transformLat(lon, lat) {
  let result = -100.0 + 2.0 * lon + 3.0 * lat + 0.2 * lat * lat + 0.1 * lon * lat + 0.2 * Math.sqrt(Math.abs(lon));
  result += ((20.0 * Math.sin(6.0 * lon * PI) + 20.0 * Math.sin(2.0 * lon * PI)) * 2.0) / 3.0;
  result += ((20.0 * Math.sin(lat * PI) + 40.0 * Math.sin((lat / 3.0) * PI)) * 2.0) / 3.0;
  return result + ((160.0 * Math.sin((lat / 12.0) * PI) + 320 * Math.sin((lat * PI) / 30.0)) * 2.0) / 3.0;
}

function transformLon(lon, lat) {
  let result = 300.0 + lon + 2.0 * lat + 0.1 * lon * lon + 0.1 * lon * lat + 0.1 * Math.sqrt(Math.abs(lon));
  result += ((20.0 * Math.sin(6.0 * lon * PI) + 20.0 * Math.sin(2.0 * lon * PI)) * 2.0) / 3.0;
  result += ((20.0 * Math.sin(lon * PI) + 40.0 * Math.sin((lon / 3.0) * PI)) * 2.0) / 3.0;
  return result + ((150.0 * Math.sin((lon / 12.0) * PI) + 300.0 * Math.sin((lon / 30.0) * PI)) * 2.0) / 3.0;
}
