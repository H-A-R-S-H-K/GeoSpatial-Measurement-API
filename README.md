# Geospatial File Measurement

A FastAPI service that accepts a KML file or a zipped Shapefile, measures each feature, and stores the result so it can be read back after the upload request finishes.

Polygon area and line length are calculated only after the dataset is in a projected CRS whose axes are metres. Geographic coordinates such as EPSG:4326 are never used as if they were metres.

## 1. Overview

Survey files usually store coordinates as longitude and latitude. Those numbers are angles. The area of a polygon in degrees is not an area on the ground, and a line length in degrees is not a distance.

This service:

1. Accepts `.kml` or a `.zip` that contains one Shapefile.
2. Parses features without the HTTP handler knowing the file format.
3. Checks the dataset CRS and, when necessary, transforms the geometries into a local UTM projection.
4. Measures each feature with a strategy registered for that geometry type.
5. Writes file metadata and one measurement row per feature to SQLite.

A later `GET` reads those rows. Nothing is kept only in memory.

## 2. Features

- **Formats:** `.kml`, and `.zip` archives containing `.shp`, `.shx`, `.dbf`, and optionally `.prj`.
- **Measurements:** Polygon area in `m²`, LineString length in `m`. Points are accepted and recorded as `NOT_REQUIRED`.
- **Other geometries:** `MultiPolygon` and anything else not registered is stored as `UNSUPPORTED_GEOMETRY`. That feature does not fail the rest of the file.
- **Invalid geometries:** Reported as `INVALID_GEOMETRY`. They are not silently repaired.
- **CRS:** Geographic datasets are transformed with GeoPandas to a UTM zone chosen from the data. A projected CRS that is already in metres is left unchanged. No UTM zone is hard-coded.
- **Attributes:** Feature properties are kept and returned as JSON. Geometry is used for measurement and is not stored.
- **Persistence:** File status, CRS, and measurements survive after the upload response is sent.
- **Upload safety:** Extension allow-list, size cap, UUID temp names, ZIP path checks, and temp-file cleanup.

## 3. Tech Stack

| Library | Why it is here |
| --- | --- |
| FastAPI | Thin HTTP layer, dependency injection, and OpenAPI docs at `/docs`. |
| Pydantic | Response models stay separate from the SQLAlchemy tables. |
| GeoPandas | Reads KML and Shapefile into a GeoDataFrame and transforms CRS with `to_crs`. |
| Shapely | Geometry type, validity, area, and length. |
| PyProj | Used through GeoPandas (`estimate_utm_crs`, axis units, authority codes). Projection math is not reimplemented. |
| SQLAlchemy 2 | Explicit sessions and repositories. The URL can change later without rewriting the pipeline. |
| SQLite | A real database with no extra process to install. Enough for local development and this assignment. |
| pytest + FastAPI TestClient | Unit tests for readers, CRS, and strategies, plus HTTP tests that read back from the database. |
| Ruff and mypy | Lint, formatting, and type checks on the application package. |

Python 3.12 or newer. `python-multipart` is included because FastAPI needs it for file uploads.

## 4. Setup

From the project directory:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Create the tables without starting the server:

```bash
python -m app.models.database
```

The server also creates tables on startup, so this step is optional.

```bash
uvicorn app.main:app --reload
```

The API listens on `http://127.0.0.1:8000`. Interactive docs are at `http://127.0.0.1:8000/docs`.

The default database file is `data/geospatial.db` under the project root. Override it with an environment variable if needed:

```bash
GEO_DATABASE_URL=sqlite:///./data/geospatial.db
GEO_MAX_UPLOAD_BYTES=20971520
GEO_MAX_ZIP_UNCOMPRESSED_BYTES=104857600
GEO_MAX_ZIP_ENTRIES=64
```

See `.env.example`. A `.env` file in the working directory is picked up automatically. The variables use the `GEO_` prefix.

## 5. API Documentation

### `GET /health`

Liveness check.

```bash
curl -s http://127.0.0.1:8000/health
```

```json
{"status": "ok"}
```

### `POST /api/files/`

Upload one `.kml` file or one `.zip` Shapefile. The form field name is `file`.

The handler checks the size while reading, then `FileService` parses, projects, measures, and stores the result before the response is returned. Processing is synchronous: the client waits, and a successful response means the rows are already committed.

```bash
curl -s -X POST http://127.0.0.1:8000/api/files/ \
  -F "file=@survey.kml"
```

`201 Created`:

```json
{
  "id": "8f3c1c2e-6b1a-4e0a-9c2d-1a2b3c4d5e6f",
  "filename": "survey.kml",
  "feature_count": 3,
  "crs": "EPSG:4326",
  "measurement_crs": "EPSG:32643",
  "status": "COMPLETED",
  "error_message": null
}
```

`crs` is the CRS from the file. `measurement_crs` is the metre-based CRS actually used for area and length. For a file that was already projected in metres, the two values are the same.

| Status | When |
| --- | --- |
| 201 | The file was parsed and every feature was recorded, including unsupported or invalid ones. |
| 400 | Extension is not `.kml` or `.zip`, or the filename is missing. No database row is created. |
| 413 | The body is larger than `GEO_MAX_UPLOAD_BYTES` (default 20 MB). No database row is created. |
| 422 | The extension was accepted, but the file is malformed, incomplete, missing a CRS, or cannot be projected. A row is stored with `status: FAILED`. |

Error body:

```json
{
  "error": "MISSING_CRS",
  "message": "The dataset does not define a coordinate reference system.",
  "file_id": "8f3c1c2e-6b1a-4e0a-9c2d-1a2b3c4d5e6f"
}
```

`file_id` is present only when a row was stored. A client can `GET` that id to see the failure later.

### `GET /api/files/{id}/`

Return the stored metadata. This reads the database. It does not reprocess the file.

```bash
curl -s http://127.0.0.1:8000/api/files/8f3c1c2e-6b1a-4e0a-9c2d-1a2b3c4d5e6f/
```

The body matches the upload response. `404` with `error: FILE_NOT_FOUND` when the id does not exist. A failed upload still returns `200` with `status: FAILED` and `error_message` set.

### `GET /api/files/{id}/measurements/`

Return one row per feature, ordered by feature index.

```bash
curl -s http://127.0.0.1:8000/api/files/8f3c1c2e-6b1a-4e0a-9c2d-1a2b3c4d5e6f/measurements/
```

```json
{
  "file_id": "8f3c1c2e-6b1a-4e0a-9c2d-1a2b3c4d5e6f",
  "measurements": [
    {
      "feature_id": 0,
      "geometry_type": "Polygon",
      "measurement": 1000000.0,
      "unit": "m²",
      "status": "COMPLETED",
      "properties": {"name": "square"}
    },
    {
      "feature_id": 1,
      "geometry_type": "LineString",
      "measurement": 500.0,
      "unit": "m",
      "status": "COMPLETED",
      "properties": {"name": "path"}
    },
    {
      "feature_id": 2,
      "geometry_type": "Point",
      "measurement": null,
      "unit": null,
      "status": "NOT_REQUIRED",
      "properties": {"name": "marker"}
    }
  ]
}
```

`feature_id` is the zero-based position after the file is parsed. If a KML file has several layers, layers are concatenated in the order the driver lists them. An attribute that happens to be named `id` stays inside `properties`. It is not used as `feature_id`.

Unsupported geometry:

```json
{
  "feature_id": 3,
  "geometry_type": "MultiPolygon",
  "measurement": null,
  "unit": null,
  "status": "UNSUPPORTED_GEOMETRY",
  "properties": {}
}
```

`404` when the file id does not exist. A file that failed before any feature was measured returns `200` and `"measurements": []`. Check the file status to tell that apart from an empty but valid dataset.

Measurements are rounded to three decimal places (millimetres). Area of a polygon with holes is the outer ring minus the holes, which is what Shapely's `area` does.

## 6. Architecture

```
HTTP client
    |
    |  POST /api/files/
    |  GET  /api/files/{id}/
    |  GET  /api/files/{id}/measurements/
    v
+---------------------------+
| API  app/api/files.py     |  read the upload, call FileService, map to Pydantic
+-------------+-------------+
              |
              v
+---------------------------+
| FileService               |  transactions, temp files, status
+--+--------+--------+------+
   |        |        |
   |        |        +----> MeasurementService
   |        |                    |
   |        |                    v
   |        |               Strategy registry
   |        |                 Polygon -> area (m²)
   |        |                 LineString -> length (m)
   |        |                 Point -> not required
   |        |
   |        +----> CRSService
   |                 validate CRS, to_crs(estimated UTM) when needed
   |
   +----> ReaderFactory
            .kml -> KMLReader ----+
            .zip -> ShapefileReader
                         |
                         v
                    GeoDataFrame
                         |
                         v
                  feature mapper (id, type, geometry, properties)
                         |
                         v
              FileRepository + MeasurementRepository
                         |
                         v
                      SQLite
```

| Piece | Responsibility |
| --- | --- |
| API layer | HTTP status codes and response schemas. No GeoPandas, no SQL, no area math. |
| `FileService` | The pipeline and the database transaction. It does not know how to parse KML or how to compute area. |
| `ReaderFactory` | Picks a reader from the extension. Adding GeoJSON is a new reader plus one registration. |
| `KMLReader` / `ShapefileReader` | Turn a file into a GeoDataFrame with geometry, attributes, and a dataset CRS. |
| Feature mapper | Converts that frame into plain feature objects so measurement does not depend on pandas. |
| `CRSService` | Decides whether a transform is required and performs it with GeoPandas. |
| `MeasurementService` | Asks the registry for a strategy. Unknown types become `UNSUPPORTED_GEOMETRY`. |
| Repositories | Insert and query. They flush. `FileService` commits. |
| SQLite | The source of truth for `GET`. |

`app/api/deps.py` is the composition root: one request gets one session, one `FileService`, and the default readers and strategies. Tests build the same graph with a temporary database, or they pass a different reader factory.

A few modules sit beside the suggested layout because they have a specific job: `app/domain` holds the in-memory feature and measurement types, `app/core/enums.py` holds statuses, and `app/api/errors.py` maps application errors to JSON.

## 7. File Processing Flow

1. **Validate the request.** The extension must be registered. The body is read in chunks and rejected once it passes the size limit. The original filename is reduced to a base name so `../../secret.kml` cannot become a path.
2. **Store the bytes** under `data/tmp/<uuid>.kml` or `<uuid>.zip`. The client's filename is only metadata.
3. **Insert a `PROCESSING` row and commit it** so a crash or a parse error can still be looked up.
4. **`ReaderFactory` selects a reader.** The Shapefile reader extracts the ZIP into a throwaway directory, refuses unsafe member names, and requires `.shp`, `.shx`, and `.dbf`. `.prj` is optional at this step.
5. **Parse to a GeoDataFrame.** KML layers are concatenated. If the KML driver does not set a CRS, the reader assigns EPSG:4326, because the KML specification says coordinates are WGS 84. A Shapefile with no `.prj` is left without a CRS.
6. **Map features.** Each row keeps its index, geometry type, Shapely geometry, and attribute values converted to JSON-safe Python.
7. **`CRSService.prepare`.** Missing CRS fails the file. A metre-based projected CRS is kept. Otherwise the frame is transformed to an estimated UTM CRS.
8. **`MeasurementService`** runs the registered strategy per feature. One bad feature produces a status on that row.
9. **Commit** `COMPLETED`, the feature count, both CRS labels, and the measurement rows.
10. **Delete the temp file** in a `finally` block, including when processing fails.

If step 7 or 8 raises an application error, the service rolls back the uncommitted measurement rows, marks the file `FAILED`, stores the message, and returns `422` with `file_id`.

## 8. CRS Handling

EPSG:4326 describes positions with longitude and latitude in degrees. Shapely's `area` and `length` are Euclidean on whatever numbers they are given. On an unprojected polygon those numbers are degrees, so the "area" changes meaning with latitude and is not in square metres. A one-degree square has area `1` in that CRS and on the order of 10^10 square metres on the ground.

`CRSService` is the only place that decides the CRS:

1. No CRS: raise `MissingCRSError`. The file fails. Individual features are not guessed.
2. Projected, and every axis unit is metre: return the frame unchanged. A dataset that is already in a national metre grid should not be reprojected into UTM for no reason.
3. Otherwise call `GeoDataFrame.estimate_utm_crs()` and `to_crs`. The zone comes from the dataset centroid. A file in Delhi and a file in Sydney do not share a hard-coded EPSG code.
4. If the geographic bounds go south of 80°S or north of 84°N, UTM is the wrong tool. The file fails with `CRS_TRANSFORMATION_FAILED` instead of returning a bad number.
5. If the longitude span is wider than one 6° UTM zone, the service still uses the centroid zone and logs a warning. Measurements near the edges are distorted. This is a known limit, not a silent special case.
6. A dataset with no finite bounds (empty, or no usable coordinates) is not transformed, because there is nothing to measure.

Strategies do not look at the CRS. Their contract is that coordinates are already metres. `FileService` calls `CRSService` before `MeasurementService`. Tests lock this in two ways: a square built as 1000 m by 1000 m in UTM, converted to EPSG:4326, and uploaded, comes back within 1 m² of 1,000,000; and that result is far from the same polygon's area in degrees.

**Limitations, on purpose:**

- **Web Mercator (EPSG:3857)** uses metres, so rule 2 keeps it. Distances in Web Mercator are not true ground distances. Reprojecting every metre CRS would also throw away a local grid the user already chose. The rule prefers "already metres" over "I know this projection is a poor choice."
- **Projected CRS in feet** (for example EPSG:2263, US survey feet) is transformed, because the API unit is metres.
- **UTM is a local projection.** It is the right default for a site or a city. It is a poor default for a country or a dataset that crosses the antimeridian. An equal-area CRS chosen from the data extent would be a better follow-up for those files.
- **KML only:** a missing CRS becomes EPSG:4326 inside `KMLReader`, not inside `CRSService`. Shapefiles do not get that default.

Z values are dropped before measuring. The result is horizontal area or length in the projected plane, not a 3D slope distance.

## 9. Design Decisions

**Reader abstraction.** KML and Shapefile do not belong in the route or in `FileService`. Both readers implement `GeospatialReader.read(path) -> GeoDataFrame`. `ReaderFactory` holds a list of registrations. A GeoJSON reader would be a new class and one line in `default_registrations`. `KMLReader`, `ShapefileReader`, and `FileService` would stay as they are. The factory is a registry, not a growing `if` inside the pipeline. That is the open/closed part that matters: the processing steps do not change when a format is added.

**Strategy per geometry.** Area, length, and "no measurement" are different operations. `MeasurementStrategyRegistry` maps `"Polygon"`, `"LineString"`, and `"Point"` to three classes. `MeasurementService` does one lookup. If nothing is registered, the feature is `UNSUPPORTED_GEOMETRY`. Adding `MultiPolygon` means a new strategy class and a `register` call. It does not mean editing the service. A unit test registers a throwaway MultiPolygon strategy and checks that the service picks it up.

**CRS is not part of measuring.** If each strategy transformed coordinates itself, every new strategy could forget and call `area` on degrees. One service owns the projection. Strategies stay in metre space and are easy to test with `box(0, 0, 10, 10)`.

**Repositories.** SQL stays out of the service. The service decides when to commit: once when the file is accepted, again when it completes, or a failure update after rollback. Repositories only `flush`. Tests can open a second session and read the same rows, which is the check that results are not sitting on the original object in memory.

**SQLite.** The assignment has to run on a laptop with one command. SQLite gives foreign keys, a unique `(file_id, feature_index)` constraint, and a file the `GET` endpoints can reopen. PostgreSQL/PostGIS is the right replacement when the data is large or concurrent writers matter. The repository and the database URL are the seam. PostGIS is not required to demonstrate the pipeline.

**Synchronous processing.** The upload response is the result. Files are capped at 20 MB. A queue, Redis, or a worker process would add operations without helping a reviewer run the project. `FileService.process_upload` is an ordinary method. A background worker could call it later without rewriting readers or strategies. The cost today is that one request occupies the worker until measurement finishes.

**Geometry is not stored.** The product of this service is the measurement. Geometry blobs would dominate the database and are not part of the `GET` contract. Attributes are small, so they are stored as JSON and returned as `properties`.

**Invalid polygons are not repaired.** `buffer(0)` and `make_valid` can change the shape and the area, and the client would not know. An invalid feature is `INVALID_GEOMETRY` with a null measurement. The rest of the file still completes.

**What was considered and not done.** A single `if geometry_type == "Polygon"` chain is shorter until the fourth type. A hard-coded EPSG:32643 is correct only for one band of longitude. A hand-written spherical area formula would duplicate PyProj and would not match "transform, then measure in metres." Keeping uploads in a process-global dict would make `GET` fail after restart and would break as soon as two workers exist.

## 10. Error Handling

Application errors are `AppError` subclasses. The API turns them into `{"error", "message", "file_id?"}` and does not include a traceback. Unexpected exceptions become `500` with `INTERNAL_ERROR`.

| Code | HTTP | Meaning |
| --- | --- | --- |
| `UNSUPPORTED_FILE_FORMAT` | 400 | Extension is not registered, or the filename is empty. Not stored. |
| `FILE_TOO_LARGE` | 413 | Upload or uncompressed ZIP exceeds its cap. Not stored. |
| `INVALID_GEOSPATIAL_FILE` | 422 | Not a KML file, not a ZIP, missing `.shp`/`.shx`/`.dbf`, more than one Shapefile, unsafe ZIP path, or the driver could not parse the file. Stored as `FAILED` once processing has started. |
| `MISSING_CRS` | 422 | The dataset has no CRS. Typical cause: a Shapefile ZIP with no `.prj`. Stored as `FAILED`. |
| `CRS_TRANSFORMATION_FAILED` | 422 | Polar data, or UTM estimation / `to_crs` failed. Stored as `FAILED`. |
| `FILE_NOT_FOUND` | 404 | Unknown id. |

Per-feature statuses are not HTTP errors:

| Status | Meaning |
| --- | --- |
| `COMPLETED` | Area or length in metres. |
| `NOT_REQUIRED` | Point. |
| `UNSUPPORTED_GEOMETRY` | No strategy for this type. |
| `INVALID_GEOMETRY` | Missing, empty, invalid, or non-finite coordinates. |

ZIP handling rejects absolute paths, `..` members, symlink entries, too many members, and an uncompressed size above the cap. Bytes are counted as they are copied, so a lying size in the ZIP header cannot expand without limit. Member names are resolved and must stay inside the extract directory.

## 11. Testing

```bash
pytest
ruff check .
ruff format --check .
mypy app
```

`pytest` collects 50 tests. They use generated fixtures, not large sample files.

| Area | What is checked |
| --- | --- |
| Readers | Valid KML, valid zipped Shapefile, malformed KML, malformed ZIP, missing `.dbf`, missing `.prj` (CRS stays empty), multiple Shapefiles, factory selection, registering a new extension. |
| CRS | EPSG:4326 is projected and the area is about 1,000,000 m², not the degree area. Southern hemisphere selects EPSG:32756, not a northern zone. An existing metre CRS is not transformed (coordinates unchanged). EPSG:3857 is kept. A foot CRS is transformed. Missing CRS, polar data, and a dataset wider than 6° are covered. |
| Strategies | Polygon area including a hole, LineString length, 3D length ignoring Z, point with no measurement, invalid polygon left invalid, unsupported MultiPolygon, a newly registered strategy. |
| File service | Real KML persisted and read from a second session, zipped Shapefile already in metres, mixed types where one unsupported and one invalid feature still produce `COMPLETED` for the file, malformed KML stored as `FAILED` and the temp file removed, `.geojson` stored nowhere. |
| API | Upload, both GETs, 404, 400, 413, 422, MultiPolygon upload, missing form field. |
| ZIP safety | Path traversal, absolute member, symlink entry, entry count, uncompressed size. |

Area and length assertions use a tolerance (`abs(actual - expected) < tolerance`), not exact float equality. The square and the line are constructed in the estimated UTM zone, converted to EPSG:4326 for the upload, and measured again. That is a round trip through the same projection the service selects.

## 12. Learning

The mistake this design is built to prevent is calling `geometry.area` on longitude and latitude and treating the result as square metres. The number is small, it looks precise, and it is not a physical area. Putting projection in its own service, and testing a known 1 km square against both the metre answer and the degree answer, makes that mistake fail the test instead of shipping.

UTM is not a universal CRS. `estimate_utm_crs()` picks a zone from the centroid, which is the right call for a site survey and a bad call for a dataset that spans a continent. Writing that limitation down, and rejecting polar latitudes where UTM is not even defined in the usual way, was more useful than pretending one projection works everywhere.

The reader registry and the measurement registry solved a real split in the code. The pipeline needs a GeoDataFrame and a list of measurements. It does not need to grow a branch for every format or every geometry. The test that registers a MultiPolygon strategy without editing `MeasurementService` is the check that the split is real.

Storing the result, and reading it back with a new database session, is what makes the `GET` endpoints honest. An object returned from the upload function is not persistence.

Leaving invalid polygons alone was the less comfortable choice. Repairing them would have produced a number. It would also have changed the user's geometry without saying so.

## 13. Future Scope

These are not implemented:

- **Background processing** for files that are too slow to finish inside the HTTP request. `FileService` can be called from a worker. The `PROCESSING` status is already stored before parsing.
- **Pagination** on `GET /measurements/` when a file has a very large feature count.
- **PostgreSQL/PostGIS** for concurrent writers and spatial queries. Swap the SQLAlchemy URL and keep the repositories.
- **GeoJSON** as another `GeospatialReader` registration.
- **MultiPolygon and MultiLineString** strategies. MultiPolygon area is a new class and a registry entry.
- **Object storage** for the original upload if files need to be downloaded again. Geometry and file bytes are not kept today.
- **Authentication and authorization** if more than one user shares the service.
- **Observability:** structured logs, request ids, and metrics for parse time and transform time.
- **A better CRS policy for large extents:** choose an equal-area projection from the bounds, or refuse datasets that cross several UTM zones, instead of measuring them in the centroid zone. Also revisit Web Mercator, which is in metres but is a poor CRS for true distance.
