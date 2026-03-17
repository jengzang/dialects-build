"""
测试坐标转换：BD-09 → WGS-84
对比新旧方法的差异
"""
from source.change_coordinates import GPSUtil, bd09togcj02


def test_coordinate_conversion():
    # 测试数据：广州市中心（百度坐标系）
    test_cases = [
        ("广州", 113.280637, 23.125178),
        ("北京", 116.413554, 39.911013),
        ("上海", 121.480539, 31.235929),
        ("深圳", 114.085947, 22.547),
    ]

    print("=" * 80)
    print("坐标转换测试：BD-09 → WGS-84")
    print("=" * 80)

    for name, bd_lon, bd_lat in test_cases:
        print(f"\n📍 {name}")
        print(f"   输入 (BD-09): 经度={bd_lon}, 纬度={bd_lat}")

        # 旧方法：BD-09 → GCJ-02
        gcj_lng, gcj_lat = bd09togcj02(bd_lon, bd_lat)
        print(f"   旧方法 (GCJ-02): 经度={gcj_lng:.6f}, 纬度={gcj_lat:.6f}")

        # 新方法：BD-09 → WGS-84
        wgs_lat, wgs_lon = GPSUtil.bd09_to_gps84(bd_lat, bd_lon)
        print(f"   新方法 (WGS-84): 经度={wgs_lon:.6f}, 纬度={wgs_lat:.6f}")

        # 计算偏移距离（简化计算）
        lon_diff = abs(wgs_lon - gcj_lng) * 111320 * 0.8  # 粗略转换为米
        lat_diff = abs(wgs_lat - gcj_lat) * 111320
        distance = (lon_diff ** 2 + lat_diff ** 2) ** 0.5

        print(f"   📏 GCJ-02 vs WGS-84 偏移约: {distance:.1f}米")

    print("\n" + "=" * 80)
    print("✅ 测试完成")
    print("\n说明：")
    print("  - BD-09：百度地图使用的坐标系")
    print("  - GCJ-02：高德/谷歌中国使用的火星坐标系")
    print("  - WGS-84：国际标准 GPS 坐标系（真实坐标）")
    print("  - 偏移距离：GCJ-02 相对 WGS-84 通常偏移 50-500 米")
    print("=" * 80)


if __name__ == "__main__":
    test_coordinate_conversion()
