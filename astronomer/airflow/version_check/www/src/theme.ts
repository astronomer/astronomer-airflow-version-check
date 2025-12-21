/*!
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
import { createSystem, defaultConfig } from "@chakra-ui/react";

export const system = createSystem(defaultConfig, {
  theme: {
    tokens: {
      colors: {
        brand: {
          50: { value: "#e6f2ff" },
          100: { value: "#b3d9ff" },
          200: { value: "#80bfff" },
          300: { value: "#4da6ff" },
          400: { value: "#1a8cff" },
          500: { value: "#0073e6" },
          600: { value: "#0059b3" },
          700: { value: "#004080" },
          800: { value: "#00264d" },
          900: { value: "#000d1a" },
        },
      },
    },
    semanticTokens: {
      colors: {
        warning: {
          bg: { value: { base: "#fef3c7", _dark: "#78350f" } },
          border: { value: { base: "#f59e0b", _dark: "#fbbf24" } },
          text: { value: { base: "#92400e", _dark: "#fef3c7" } },
        },
        critical: {
          bg: { value: { base: "#fee2e2", _dark: "#7f1d1d" } },
          border: { value: { base: "#ef4444", _dark: "#f87171" } },
          text: { value: { base: "#991b1b", _dark: "#fee2e2" } },
        },
      },
    },
  },
});
