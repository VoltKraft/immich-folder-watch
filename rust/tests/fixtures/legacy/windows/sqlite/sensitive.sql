-- Generated synthetic C# compatibility fixture; never an installed profile.
BEGIN TRANSACTION;
CREATE TABLE owned_albums (
    account_scope TEXT NOT NULL,
    source_key TEXT NOT NULL,
    directory_key TEXT NOT NULL,
    album_id TEXT NOT NULL,
    PRIMARY KEY (account_scope, source_key, directory_key),
    UNIQUE (account_scope, source_key, album_id)
);
CREATE TABLE sync_account_status (
    account_scope TEXT NOT NULL PRIMARY KEY,
    last_successful_sync_utc TEXT NOT NULL
);
CREATE TABLE sync_entries (
    account_scope TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_key TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    relative_path_key TEXT NOT NULL,
    asset_id TEXT NULL,
    album_name TEXT NOT NULL,
    file_size INTEGER NOT NULL CHECK (file_size >= 0),
    last_write_time_utc TEXT NOT NULL,
    direction INTEGER NOT NULL CHECK (direction IN (0, 1)),
    status INTEGER NOT NULL CHECK (status IN (0, 1)),
    last_synchronized_at_utc TEXT NOT NULL,
    tombstone_expires_at_utc TEXT NULL,
    PRIMARY KEY (account_scope, source_key, relative_path_key),
    CHECK (
        (status = 0 AND tombstone_expires_at_utc IS NULL)
        OR (status = 1 AND tombstone_expires_at_utc IS NOT NULL)
    )
);
CREATE TABLE sync_timestamp_repairs (
    account_scope TEXT NOT NULL,
    source_key TEXT NOT NULL,
    relative_path_key TEXT NOT NULL,
    repair_json TEXT NOT NULL,
    PRIMARY KEY (account_scope, source_key, relative_path_key)
);
CREATE INDEX ix_sync_entries_asset_id
    ON sync_entries (account_scope, asset_id)
    WHERE asset_id IS NOT NULL;
INSERT INTO "owned_albums" VALUES ('16be13cf5f92d495cd2fabdb5430837edaf35d6a85482e1660dfd969dc3225b9','C:\ifw-synthetic\Média','Other','album-other');
INSERT INTO "owned_albums" VALUES ('29975cc6cf48f8943e4321a7c8cf9e3db160d3f68c7331bda0c2b3650c9beb13','C:\ifw-synthetic\Média','Straße','album-exact-id');
INSERT INTO "sync_account_status" VALUES ('16be13cf5f92d495cd2fabdb5430837edaf35d6a85482e1660dfd969dc3225b9','2024-02-29T05:04:05.1234567+00:00');
INSERT INTO "sync_account_status" VALUES ('29975cc6cf48f8943e4321a7c8cf9e3db160d3f68c7331bda0c2b3650c9beb13','2024-02-29T06:04:05.1234567+00:00');
INSERT INTO "sync_entries" VALUES ('16be13cf5f92d495cd2fabdb5430837edaf35d6a85482e1660dfd969dc3225b9','C:\ifw-synthetic\Média','C:\ifw-synthetic\Média','other-account.jpg','other-account.jpg','asset-download','',0,'2024-02-29T03:04:05.1234567+00:00',1,0,'2024-02-29T05:04:05.1234567+00:00',NULL);
INSERT INTO "sync_entries" VALUES ('29975cc6cf48f8943e4321a7c8cf9e3db160d3f68c7331bda0c2b3650c9beb13','C:\ifw-synthetic\Média','C:\ifw-synthetic\Média','Straße\σς-𐐨.jpg','Straße\σς-𐐨.jpg','asset-upload','null',9007199254740993,'2024-02-29T03:04:05.1234567+00:00',0,0,'2024-02-29T04:04:05.1234567+00:00',NULL);
INSERT INTO "sync_entries" VALUES ('29975cc6cf48f8943e4321a7c8cf9e3db160d3f68c7331bda0c2b3650c9beb13','C:\ifw-synthetic\Média','C:\ifw-synthetic\Média','download.bin','download.bin','asset-download','',0,'2024-02-29T03:04:05.1234567+00:00',1,0,'2024-02-29T05:04:05.1234567+00:00',NULL);
INSERT INTO "sync_entries" VALUES ('29975cc6cf48f8943e4321a7c8cf9e3db160d3f68c7331bda0c2b3650c9beb13','C:\ifw-synthetic\Média','C:\ifw-synthetic\Média','removed.jpg','removed.jpg',NULL,'null',9007199254740993,'2024-02-29T03:04:05.1234567+00:00',0,1,'2024-03-02T03:04:05.1234567+00:00','2024-02-29T03:06:05.1234567+00:00');
INSERT INTO "sync_timestamp_repairs" VALUES ('29975cc6cf48f8943e4321a7c8cf9e3db160d3f68c7331bda0c2b3650c9beb13','C:\ifw-synthetic\Média','Straße\σς-𐐨.jpg','{"OriginalEntry":{"AccountScope":"29975cc6cf48f8943e4321a7c8cf9e3db160d3f68c7331bda0c2b3650c9beb13","SourcePath":"C:\\ifw-synthetic\\M\u00E9dia","RelativePath":"Stra\u00DFe\\\u03C3\u03C2-\uD801\uDC28.jpg","AssetId":"asset-upload","AlbumName":"null","FileSize":9007199254740993,"LastWriteTimeUtc":"2024-02-29T03:04:05.1234567+00:00","Direction":0,"Status":0,"LastSynchronizedAtUtc":"2024-02-29T04:04:05.1234567+00:00","TombstoneExpiresAtUtc":null},"CreationTimeUtc":"2024-02-27T03:04:05.1234567+00:00","LastWriteTimeUtc":"2024-02-29T03:04:05.1234568+00:00","ContentSha256":"7879B91B74835447CAC95069F93E67B1705052D13CCBA8C6C193622D919BEA29"}');
PRAGMA user_version = 1;
COMMIT;
