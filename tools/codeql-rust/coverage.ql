/** Lists first-party Rust files and the compiler configuration the extractor actually saw. */
import rust

from ExtractedFile file, string status
where
  exists(file.getRelativePath()) and
  (
    file.hasSemantics() and status = "active"
    or
    file.isSkippedByCompilation() and status = "cfg-skipped"
    or
    not file.hasSemantics() and not file.isSkippedByCompilation() and status = "unresolved"
  )
select file.getRelativePath() as path, status order by path
