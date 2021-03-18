__all__ = ["CONFIG_SCHEMA"]

import yaml

CONFIG_SCHEMA = yaml.safe_load(
    """
$schema: http://json-schema.org/draft-07/schema#
$id: https://github.com/lsst-ts/ts_CBP/blob/master/schema/CBP.yaml
title: CBP v1
description: Schema for CBP configuration files
type: object
properties:
  address:
    description: IP address of CBP
    type: string
    default: "127.0.0.1"
  port:
    description: port of CBP
    type: integer
    default: 9999
  mask1:
    description: Mask 1 of CBP
    type: object
    properties:
      name:
        description: name of mask
        type: string
        default: "Mask 1"
      rotation:
        description: rotation of mask (degree)
        type: number
        default: 30
  mask2:
    description: Mask 2 of CBP
    type: object
    properties:
      name:
        type: string
        default: "Mask 2"
      rotation:
        description: rotation of mask (degree)
        type: number
        default: 60
  mask3:
    description: Mask 3 of CBP
    type: object
    properties:
      name:
        type: string
        default: "Mask 3"
      rotation:
        description: rotation of mask (degree)
        type: number
        default: 90
  mask4:
    description: Mask 4 of CBP
    type: object
    properties:
      name:
        type: string
        default: "Mask 4"
      rotation:
        type: number
        description: rotation of mask (degree)
        default: 120
  mask5:
    description: Mask 5 of CBP
    type: object
    properties:
      name:
        type: string
        default: "Mask 5"
      rotation:
        type: number
        description: rotation of mask (degree)
        default: 150
required: [address, port, mask1, mask2, mask3, mask4, mask5]
additionalProperties: false
"""
)
