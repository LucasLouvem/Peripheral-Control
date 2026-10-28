"""Identidade e descritor esperados do mouse.

Níveis de evidência usados nos comentários do pacote:
  [LOCAL]  observado neste aparelho (descritores e sysfs);
  [FONTE]  descrito por projetos externos, ainda não verificado neste aparelho;
  [TESTE]  confirmado por teste físico documentado em docs/devices/cobra-m711.md.
"""

from ...core.discovery import DeviceSpec

VENDOR_ID = 0x04D9  # [LOCAL]
PRODUCT_ID = 0xFC30  # [LOCAL]
BCD_DEVICE = 0x0112  # [LOCAL] única revisão considerada; outras são recusadas
VENDOR_USAGE_PAGE = 0xFFA0  # [LOCAL] coleção de fabricante na interface 2

# [LOCAL] Feature Reports do descritor da interface 2, em bytes no fio (com o ID).
FEATURE_SIZES = {2: 16, 3: 64, 4: 256, 5: 1024, 6: 2048}

SPEC = DeviceSpec(
    name="S118 mouse (04d9:fc30)",
    vendor_id=VENDOR_ID,
    product_id=PRODUCT_ID,
    bcd_device=BCD_DEVICE,
    usage_page=VENDOR_USAGE_PAGE,
    feature_sizes=FEATURE_SIZES,
)
