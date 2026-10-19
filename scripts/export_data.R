#!/usr/bin/env Rscript
# Export the njoaguof tables to gzipped CSV, the input of scripts/build_data.py.
#
# Usage: Rscript scripts/export_data.R <git-ref> [out-dir]
#
# Installs tor-gu/njoaguof at <git-ref> (e.g. v2.1.2) into a temporary
# library, and writes to out-dir (default: data):
#   <table>.csv.gz  one per table, in R's row order (NA is an empty field;
#                   empty strings are exported as NA, and reported)
#   columns.csv     table, position, column, type (integer, logical, date,
#                   factor or character)
#   levels.csv      table, column, position, level (every factor column)
#   SOURCE          the release and commit
#
# To export a tag that isn't pushed yet, set NJOAGUOF_GIT to a local clone,
# e.g. NJOAGUOF_GIT=../../njoaguof/njoaguof.

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1 || length(args) > 2) {
  stop("Usage: Rscript scripts/export_data.R <git-ref> [out-dir]")
}
ref <- args[[1]]
out_dir <- if (length(args) == 2) args[[2]] else "data"

tables <- c(
  "incident", "subject", "officer_name_variants",
  "incident_contact_origin", "incident_lighting", "incident_location_type",
  "incident_officer_injury_type", "incident_officer_medical_treatment",
  "incident_planned_contact", "incident_type", "incident_video_type",
  "incident_weather",
  "incident_subject_action", "incident_subject_force_type",
  "incident_subject_injury", "incident_subject_medical_treatment",
  "incident_subject_perceived_condition",
  "incident_subject_reason_not_arrested", "incident_subject_resistance"
)

lib <- file.path(tempdir(), "njoaguof-lib")
dir.create(lib, showWarnings = FALSE)
local_git <- Sys.getenv("NJOAGUOF_GIT")
if (nzchar(local_git)) {
  remotes::install_git(
    paste0("file://", normalizePath(local_git)),
    ref = ref, lib = lib, upgrade = "never", dependencies = FALSE, quiet = TRUE
  )
} else {
  remotes::install_github(
    "tor-gu/njoaguof",
    ref = ref, lib = lib, upgrade = "never", dependencies = FALSE, quiet = TRUE
  )
}
desc <- packageDescription("njoaguof", lib.loc = lib)
commit <- if (!is.null(desc$RemoteSha)) desc$RemoteSha else NA

column_type <- function(col) {
  if (inherits(col, "Date")) {
    "date"
  } else if (is.factor(col)) {
    "factor"
  } else if (is.logical(col)) {
    "logical"
  } else if (is.integer(col)) {
    "integer"
  } else if (is.numeric(col)) {
    # Ids are stored as doubles; refuse anything that isn't a whole number
    if (any(!is.na(col) & col != round(col))) {
      stop("numeric column with non-integer values")
    }
    "integer"
  } else if (is.character(col)) {
    "character"
  } else {
    stop("unexpected column class ", class(col)[[1]])
  }
}

dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)
columns <- list()
levels_out <- list()
for (name in tables) {
  env <- new.env()
  data(list = name, package = "njoaguof", lib.loc = lib, envir = env)
  df <- as.data.frame(env[[name]])
  types <- vapply(
    names(df),
    function(column) {
      tryCatch(column_type(df[[column]]), error = function(e) {
        stop(name, ".", column, ": ", conditionMessage(e))
      })
    },
    character(1)
  )
  for (column in names(df)) {
    col <- df[[column]]
    # Empty strings would be indistinguishable from NA in the CSV, so they
    # become NA (reported; the source data should have NA there anyway)
    if (is.factor(col) && "" %in% levels(col)) {
      stop(name, ".", column, ": has an empty factor level")
    }
    if (is.character(col)) {
      empty <- which(col == "")
      if (length(empty) > 0) {
        message(
          "Converted ", length(empty), " empty string(s) to NA in ",
          name, ".", column, " (rows ", paste(head(empty, 10), collapse = ", "),
          if (length(empty) > 10) ", ..." else "", ")"
        )
        col[empty] <- NA
        df[[column]] <- col
      }
    }
    if (types[[column]] == "integer" && !is.integer(col)) {
      df[[column]] <- as.integer(col)
    }
    if (is.factor(col)) {
      lv <- levels(col)
      levels_out[[length(levels_out) + 1]] <- data.frame(
        table = name, column = column, position = seq_along(lv), level = lv
      )
    }
  }
  columns[[name]] <- data.frame(
    table = name, position = seq_along(types), column = names(df), type = types
  )

  csv <- file.path(out_dir, paste0(name, ".csv"))
  write.csv(df, csv, row.names = FALSE, na = "", fileEncoding = "UTF-8")
  # gzip -n: no name or timestamp, so the same data gives the same bytes
  unlink(paste0(csv, ".gz"))
  status <- system2("gzip", c("-n", "-9", shQuote(csv)))
  if (status != 0) stop("gzip failed for ", csv)
  message("Wrote ", nrow(df), " rows to ", csv, ".gz")
}

write.csv(
  do.call(rbind, columns), file.path(out_dir, "columns.csv"),
  row.names = FALSE, fileEncoding = "UTF-8"
)
write.csv(
  do.call(rbind, levels_out), file.path(out_dir, "levels.csv"),
  row.names = FALSE, fileEncoding = "UTF-8"
)

source_lines <- c(
  "package=njoaguof",
  paste0("version=", desc$Version),
  paste0("ref=", ref),
  paste0("commit=", commit),
  paste0("exported=", format(Sys.Date()))
)
writeLines(source_lines, file.path(out_dir, "SOURCE"))
message("Wrote ", file.path(out_dir, "SOURCE"))
