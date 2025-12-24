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
