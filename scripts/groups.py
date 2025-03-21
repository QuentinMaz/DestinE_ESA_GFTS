import xarray as xr
import numpy as np

from simplify import (
    has_states,
    list_tags,
    logger,
    open_dataset,
    rotate_data,
    get_filesystem,
)

NSIDE = 4096


def convert_to_parquet():
    data = xr.open_zarr("data/sea_bass_average.zarr")
    for quarter, group in data.groupby("quarter"):
        logger.info(f"Writing parquet file for quarter {quarter}")
        subset = (
            group.to_dataframe()
            .reset_index()
            .set_index(["cell_ids", "quarter"])
            .unstack("quarter")
        )
        del subset["cell"]
        subset = subset.reset_index()
        subset.columns = ["cell_ids", "states"]
        subset = subset[subset > 1e-7].dropna()
        subset.to_parquet(f"data/sea_bass_average_q{quarter}.parquet", index=False)
        with get_filesystem().open(
            f"s3://destine-gfts-visualisation-data/groups/sea_bass_average_q{quarter}.parquet",
            "wb",
        ) as fl:
            subset.to_parquet(fl, index=False)


def rotate_group():
    data = xr.open_zarr("data/sea_bass_average_with_shift.zarr")
    rotated = rotate_data(data.rename_dims({"quarter": "time"}))
    rotated = rotated.rename_dims({"time": "quarter"})

    rotated.to_zarr("data/sea_bass_average.zarr", mode="w")
    store = get_filesystem().get_mapper(
        "s3://destine-gfts-visualisation-data/groups/sea_bass_average.zarr"
    )
    rotated.to_zarr(store=store, mode="w", consolidated=True, compute=True)


def create_groups():
    tags = list_tags()

    result = None
    timpesteps = 0
    for idx, tag in enumerate(tags):
        if not has_states(tag):
            logger.debug(f"No states.zarr file found for {tag}")
            continue
        logger.debug(f"Processing tag {tag} ({idx + 1}/{len(tags)})")

        data = open_dataset(tag)
        timpesteps += data.time.shape[0]
        data = data.fillna(0)

        avg_by_quarter = data.groupby("time.quarter").sum("time").compute()

        if result is None:
            result = avg_by_quarter
        else:
            # Combine both datasets and sum by quarter
            result = xr.concat(
                [avg_by_quarter, result],
                dim="quarter",
            )
            result = result.groupby("quarter").sum("quarter")

        result = result.fillna(0)
        result = result.compute()

    result = result / timpesteps

    result = result.where(result != 0, other=np.nan)

    result.to_zarr("data/sea_bass_average_with_shift.zarr", mode="w")

    store = get_filesystem().get_mapper(
        "s3://destine-gfts-visualisation-data/groups/sea_bass_average_with_shift.zarr"
    )
    result.to_zarr(store=store, mode="w", consolidated=True, compute=True)


if __name__ == "__main__":
    # create_groups()
    # rotate_group()
    convert_to_parquet()
