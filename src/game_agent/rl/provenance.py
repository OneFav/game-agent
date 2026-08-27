SOURCE_REPOSITORY = "Sailero/mvp_inner_loop"
SOURCE_REVISION = "8aa6a22f055312b7970bf073f1e4af65560aef27"

# MAPPO is deliberately not exposed: the source revision fails its 2v2 training
# path because local and global observation dimensions are mixed.
QUARANTINED_ALGORITHMS = {
    "mappo": "2v2 global observation dimension mismatch in the source revision",
}
