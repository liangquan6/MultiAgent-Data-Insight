"""生成 iris.csv (150 行), 跑通 demo 用."""
from sklearn.datasets import load_iris
import pandas as pd

if __name__ == "__main__":
    iris = load_iris(as_frame=True)
    df = iris.frame
    df.columns = ["sepal_len", "sepal_wid", "petal_len", "petal_wid", "species"]
    df["species"] = df["species"].map({0: "setosa", 1: "versicolor", 2: "virginica"})
    out = "data/iris.csv"
    df.to_csv(out, index=False)
    print(f"saved {out}, shape={df.shape}")