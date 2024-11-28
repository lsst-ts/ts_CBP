#
# This file is part of ts_cbp.
#
# Developed for the Rubin Observatory Telescope and Site System.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
__all__ = ["CONFIG_SCHEMA"]

import yaml

CONFIG_SCHEMA = yaml.safe_load(
    """
$schema: http://json-schema.org/draft-07/schema#
$id: https://github.com/lsst-ts/ts_CBP/blob/master/schema/CBP.yaml
title: CBP v2
description: Schema for CBP configuration files
type: object
properties:
  address:
    description: IP address of CBP
    type: string
    default: "127.0.0.1"
  port:
    description: Network port of CBP
    type: integer
    default: 9999
  mask1:
    description: Mask 1 of CBP
    type: object
    properties:
      name:
        description: Name of mask
        type: string
        default: "Mask 1"
      rotation:
        description: Rotation of mask (degree)
        type: number
        default: 30
  mask2:
    description: Mask 2 of CBP
    type: object
    properties:
      name:
        description: Name of Mask
        type: string
        default: "Mask 2"
      rotation:
        description: Rotation of mask (degree)
        type: number
        default: 60
  mask3:
    description: Mask 3 of CBP
    type: object
    properties:
      name:
        description: Name of Mask
        type: string
        default: "Mask 3"
      rotation:
        description: Rotation of mask (degree)
        type: number
        default: 90
  mask4:
    description: Mask 4 of CBP
    type: object
    properties:
      name:
        description: Name of Mask
        type: string
        default: "Mask 4"
      rotation:
        type: number
        description: Rotation of mask (degree)
        default: 120
  mask5:
    description: Mask 5 of CBP
    type: object
    properties:
      name:
        description: Name of Mask
        type: string
        default: "Mask 5"
      rotation:
        type: number
        description: Rotation of mask (degree)
        default: 150
required: [address, port, mask1, mask2, mask3, mask4, mask5]
additionalProperties: false
"""
)
