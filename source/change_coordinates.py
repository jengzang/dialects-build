import math
import re

import pandas as pd


class GPSUtil:
    pi = 3.1415926535897932384626
    x_pi = 3.14159265358979324 * 3000.0 / 180.0  # 用於 BD-09 和 GCJ-02 之間的轉換
    a = 6378245.0  # 地球半徑
    ee = 0.00669342162296594323  # 偏心率

    @staticmethod
    def transform_lat(x, y):
        """
        根據經度和緯度計算轉換後的緯度差。
        """
        ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
        ret += (20.0 * math.sin(6.0 * x * GPSUtil.pi) + 20.0 * math.sin(2.0 * x * GPSUtil.pi)) * 2.0 / 3.0
        ret += (20.0 * math.sin(y * GPSUtil.pi) + 40.0 * math.sin(y / 3.0 * GPSUtil.pi)) * 2.0 / 3.0
        ret += (160.0 * math.sin(y / 12.0 * GPSUtil.pi) + 320 * math.sin(y * GPSUtil.pi / 30.0)) * 2.0 / 3.0
        return ret

    @staticmethod
    def transform_lon(x, y):
        """
        根據經度和緯度計算轉換後的經度差。
        """
        ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
        ret += (20.0 * math.sin(6.0 * x * GPSUtil.pi) + 20.0 * math.sin(2.0 * x * GPSUtil.pi)) * 2.0 / 3.0
        ret += (20.0 * math.sin(x * GPSUtil.pi) + 40.0 * math.sin(x / 3.0 * GPSUtil.pi)) * 2.0 / 3.0
        ret += (150.0 * math.sin(x / 12.0 * GPSUtil.pi) + 300.0 * math.sin(x / 30.0 * GPSUtil.pi)) * 2.0 / 3.0
        return ret

    @staticmethod
    def out_of_china(lat, lon):
        """
        判斷是否超出中國範圍
        """
        if lon < 72.004 or lon > 137.8347:
            return True
        if lat < 0.8293 or lat > 55.8271:
            return True
        return False

    @staticmethod
    def gps84_to_gcj02(lat, lon):
        """
        將 WGS-84 (GPS) 坐標系轉換為 GCJ-02 (火星坐標系)
        """
        if GPSUtil.out_of_china(lat, lon):
            return [lat, lon]

        dLat = GPSUtil.transform_lat(lon - 105.0, lat - 35.0)
        dLon = GPSUtil.transform_lon(lon - 105.0, lat - 35.0)

        radLat = lat / 180.0 * GPSUtil.pi
        magic = math.sin(radLat)
        magic = 1 - GPSUtil.ee * magic * magic
        sqrtMagic = math.sqrt(magic)

        dLat = (dLat * 180.0) / ((GPSUtil.a * (1 - GPSUtil.ee)) / (magic * sqrtMagic) * GPSUtil.pi)
        dLon = (dLon * 180.0) / (GPSUtil.a / sqrtMagic * math.cos(radLat) * GPSUtil.pi)

        mgLat = lat + dLat
        mgLon = lon + dLon
        return [mgLat, mgLon]

    @staticmethod
    def gcj02_to_gps84(lat, lon):
        """
        將 GCJ-02 (火星坐標系) 轉換為 WGS-84 (GPS) 坐標系
        """
        gps = GPSUtil.transform(lat, lon)
        lontitude = lon * 2 - gps[1]
        latitude = lat * 2 - gps[0]
        return [latitude, lontitude]

    @staticmethod
    def gcj02_to_bd09(lat, lon):
        """
        GCJ-02 轉換為 BD-09 (百度坐標系)
        """
        x = lon
        y = lat
        z = math.sqrt(x * x + y * y) + 0.00002 * math.sin(y * GPSUtil.x_pi)
        theta = math.atan2(y, x) + 0.000003 * math.cos(x * GPSUtil.x_pi)
        tempLon = z * math.cos(theta) + 0.0065
        tempLat = z * math.sin(theta) + 0.006
        return [tempLat, tempLon]

    @staticmethod
    def bd09_to_gcj02(lat, lon):
        """
        BD-09 轉換為 GCJ-02 (火星坐標系)
        """
        x = lon - 0.0065
        y = lat - 0.006
        z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * GPSUtil.x_pi)
        theta = math.atan2(y, x) - 0.000003 * math.cos(x * GPSUtil.x_pi)
        tempLon = z * math.cos(theta)
        tempLat = z * math.sin(theta)
        return [tempLat, tempLon]

    @staticmethod
    def gps84_to_bd09(lat, lon):
        """
        WGS-84 轉換為 BD-09
        """
        gcj02 = GPSUtil.gps84_to_gcj02(lat, lon)
        return GPSUtil.gcj02_to_bd09(gcj02[0], gcj02[1])

    @staticmethod
    def bd09_to_gps84(lat, lon):
        """
        BD-09 轉換為 WGS-84 (GPS)
        """
        gcj02 = GPSUtil.bd09_to_gcj02(lat, lon)
        gps84 = GPSUtil.gcj02_to_gps84(gcj02[0], gcj02[1])
        # 保留六位小數
        gps84[0] = GPSUtil.retain6(gps84[0])
        gps84[1] = GPSUtil.retain6(gps84[1])
        return gps84

    @staticmethod
    def retain6(num):
        """
        保留小數點後六位
        """
        return round(num, 6)

    @staticmethod
    def transform(lat, lon):
        """
        進行 GCJ-02 火星坐標系轉換的內部方法
        """
        if GPSUtil.out_of_china(lat, lon):
            return [lat, lon]

        dLat = GPSUtil.transform_lat(lon - 105.0, lat - 35.0)
        dLon = GPSUtil.transform_lon(lon - 105.0, lat - 35.0)

        radLat = lat / 180.0 * GPSUtil.pi
        magic = math.sin(radLat)
        magic = 1 - GPSUtil.ee * magic * magic
        sqrtMagic = math.sqrt(magic)

        dLat = (dLat * 180.0) / ((GPSUtil.a * (1 - GPSUtil.ee)) / (magic * sqrtMagic) * GPSUtil.pi)
        dLon = (dLon * 180.0) / (GPSUtil.a / sqrtMagic * math.cos(radLat) * GPSUtil.pi)

        mgLat = lat + dLat
        mgLon = lon + dLon
        return [mgLat, mgLon]


# * 百度坐标系 (BD-09) 与 火星坐标系 (GCJ-02)的转换
# * 即 百度 转 谷歌、高德
# * @param bd_lon
# * @param bd_lat
# * @returns {*[]}
# */
def bd09togcj02(bd_lon, bd_lat):
    x_pi = 3.14159265358979324 * 3000.0 / 180.0
    x = bd_lon - 0.0065
    y = bd_lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * x_pi)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * x_pi)
    gg_lng = z * math.cos(theta)
    gg_lat = z * math.sin(theta)
    return [gg_lng, gg_lat]


# * 火星坐标系 (GCJ-02) 与百度坐标系 (BD-09) 的转换
# * 即谷歌、高德 转 百度
# */
def gcj02tobd09(lng, lat):
    x_PI = 3.14159265358979324 * 3000.0 / 180.0
    z = math.sqrt(lng * lng + lat * lat) + 0.00002 * math.sin(lat * x_PI)
    theta = math.atan2(lat, lng) + 0.000003 * math.cos(lng * x_PI)
    bd_lng = z * math.cos(theta) + 0.0065
    bd_lat = z * math.sin(theta) + 0.006
    return [bd_lng, bd_lat]


# wgs84转高德
def wgs84togcj02(lng, lat):
    PI = 3.1415926535897932384626
    ee = 0.00669342162296594323
    a = 6378245.0
    dlat = transformlat(lng - 105.0, lat - 35.0)
    dlng = transformlng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * PI
    magic = math.sin(radlat)
    magic = 1 - ee * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * PI)
    dlng = (dlng * 180.0) / (a / sqrtmagic * math.cos(radlat) * PI)
    mglat = lat + dlat
    mglng = lng + dlng
    return [mglng, mglat]


# GCJ02/谷歌、高德 转换为 WGS84 gcj02towgs84
def gcj02towgs84(localStr):
    lng = float(re.split(r'[，,]', localStr)[0])
    lat = float(re.split(r'[，,]', localStr)[1])
    PI = 3.1415926535897932384626
    ee = 0.00669342162296594323
    a = 6378245.0
    dlat = transformlat(lng - 105.0, lat - 35.0)
    dlng = transformlng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * PI
    magic = math.sin(radlat)
    magic = 1 - ee * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * PI)
    dlng = (dlng * 180.0) / (a / sqrtmagic * math.cos(radlat) * PI)
    mglat = lat + dlat
    mglng = lng + dlng
    return str(lng * 2 - mglng) + ',' + str(lat * 2 - mglat)


def transformlat(lng, lat):
    PI = 3.1415926535897932384626
    ret = -100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * \
          lat + 0.1 * lng * lat + 0.2 * math.sqrt(abs(lng))
    ret += (20.0 * math.sin(6.0 * lng * PI) + 20.0 *
            math.sin(2.0 * lng * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lat * PI) + 40.0 *
            math.sin(lat / 3.0 * PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(lat / 12.0 * PI) + 320 *
            math.sin(lat * PI / 30.0)) * 2.0 / 3.0
    return ret


def transformlng(lng, lat):
    PI = 3.1415926535897932384626
    ret = 300.0 + lng + 2.0 * lat + 0.1 * lng * lng + \
          0.1 * lng * lat + 0.1 * math.sqrt(abs(lng))
    ret += (20.0 * math.sin(6.0 * lng * PI) + 20.0 *
            math.sin(2.0 * lng * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lng * PI) + 40.0 *
            math.sin(lng / 3.0 * PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(lng / 12.0 * PI) + 300.0 *
            math.sin(lng / 30.0 * PI)) * 2.0 / 3.0
    return ret


# 主函數
# def main():
#     # 讀取 Excel 文件
#     # file_path = input(
#     #     "請輸入文件路徑 (例如 C:\\Users\\joengzaang\\PycharmProjects\\process_phonology\\data\\dependency\\Append_files.xlsx): ")
#     file_path = "C:\\Users\\joengzaang\\PycharmProjects\\process_phonology\\data\\dependency\\Append_files.xlsx"
#     df = pd.read_excel(file_path)
#
#     # 輸入需要轉換的坐標系
#     print("請選擇轉換方式:")
#     print("1: BD-09 -> GCJ-02")
#     print("2: GCJ-02 -> BD-09")
#     print("3: WGS-84 -> GCJ-02")
#     print("4: GCJ-02 -> WGS-84")
#     # choice = int(input("請選擇 1、2、3 或 4: "))
#     choice = int(1)
#
#     # 根據選擇進行相應的轉換
#     for index, row in df.iterrows():
#         bd_lon, bd_lat = map(float, re.split(r'[，,]', row['經緯度']))
#         if choice == 1:
#             result = bd09togcj02(bd_lon, bd_lat)
#             print(f"BD-09 -> GCJ-02: {result}")
#         elif choice == 2:
#             result = gcj02tobd09(bd_lon, bd_lat)
#             print(f"GCJ-02 -> BD-09: {result}")
#         elif choice == 3:
#             result = wgs84togcj02(bd_lon, bd_lat)
#             print(f"WGS-84 -> GCJ-02: {result}")
#         elif choice == 4:
#             result = gcj02towgs84(f"{bd_lon},{bd_lat}")
#             print(f"GCJ-02 -> WGS-84: {result}")
#         else:
#             print("無效的選擇")
#             break
#
#
# if __name__ == "__main__":
#     main()