CREATE TABLE organizacije (
    id serial PRIMARY KEY,
    ime_kratko text,
    ime_dolgo text
);
CREATE TABLE osebe (
    id serial PRIMARY KEY,
    ime text,
    priimek text
);
CREATE TABLE gradiva (
    id serial PRIMARY KEY,
    naslov text,
    leto integer,
    repozitorij_url text
);
CREATE TABLE datoteke (
    id serial PRIMARY KEY,
    url text,
    gradivo_id integer,
    CONSTRAINT datoteke_gradivo_id_fkey FOREIGN KEY (gradivo_id) REFERENCES gradiva (id)
);
CREATE TABLE strani (
    id serial PRIMARY KEY,
    datoteka_id integer,
    stevilka_strani_skupaj text,
    stevilka_strani_pdf text,
    text text,
    text_tsv tsvector,
    CONSTRAINT strani_datoteka_id_fkey FOREIGN KEY (datoteka_id) REFERENCES datoteke (id)
);
CREATE TABLE gradiva_osebe (
    gradivo_id integer PRIMARY KEY,
    oseba_id integer NOT NULL,
    CONSTRAINT gradiva_osebe_gradivo_id_fkey FOREIGN KEY (gradivo_id) REFERENCES gradiva (id),
    CONSTRAINT gradiva_osebe_oseba_id_fkey FOREIGN KEY (oseba_id) REFERENCES osebe (id)
);
CREATE TABLE gradiva_organizacije (
    gradivo_id integer PRIMARY KEY,
    organizacija_id integer NOT NULL,
    CONSTRAINT gradiva_organizacije_gradivo_id_fkey FOREIGN KEY (gradivo_id) REFERENCES gradiva (id),
    CONSTRAINT gradiva_organizacije_organizacija_id_fkey FOREIGN KEY (organizacija_id) REFERENCES organizacije (id)
);
CREATE INDEX idx_strani_text_tsv ON strani USING gin (text_tsv);
CREATE TRIGGER tsvectorupdate 
    BEFORE INSERT OR UPDATE 
    ON strani 
        FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger('text_tsv', 'pg_catalog.simple', 'text');