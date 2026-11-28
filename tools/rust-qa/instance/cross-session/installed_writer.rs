//! Read-only cutover preflight for the two original per-machine 3.0.4 MSIs.

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct Product {
    arch: &'static str,
    code: &'static str,
    package: &'static str,
}

const PRODUCTS: [Product; 2] = [
    Product {
        arch: "x64",
        code: "{50554B02-DB63-4388-A959-8F0B25856F5A}",
        package: "{19DC3747-2CBD-4D6A-9960-AB0AA4B65947}",
    },
    Product {
        arch: "arm64",
        code: "{A947D312-F16F-4F10-8F47-92F33393028A}",
        package: "{A16B20CA-66EB-43A4-A98E-4FA850897F89}",
    },
];
const UPGRADE_CODE: &str = "{F82E51D6-6D61-4A5D-B8AA-9D84A5D0D57D}";
const UNKNOWN_PRODUCT: u32 = 1605;

trait Inventory {
    fn property(&self, product: &str, name: &str) -> Result<String, u32>;
    fn family_registered(&self, upgrade: &str) -> Result<bool, u32>;
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Refusal {
    Shipping(Product),
    OtherRegistration,
    InventoryError(u32),
    CutoverRequired,
}

fn check_product(msi: &impl Inventory, product: Product) -> Result<(), Refusal> {
    // Windows SDK msi.h: INSTALLPROPERTY_PRODUCTSTATE is "State".
    // MsiGetProductInfoExW returns "5" for installed and "1" for advertised.
    let state = match msi.property(product.code, "State") {
        Err(UNKNOWN_PRODUCT) => return Ok(()),
        other => other.map_err(Refusal::InventoryError)?,
    };
    if state == "5" {
        let version = msi
            .property(product.code, "VersionString")
            .map_err(Refusal::InventoryError)?;
        let package = msi
            .property(product.code, "PackageCode")
            .map_err(Refusal::InventoryError)?;
        if version == "3.0.4" && package.eq_ignore_ascii_case(product.package) {
            return Err(Refusal::Shipping(product));
        }
    }
    // An advertised product or a different package can still launch the legacy application.
    Err(Refusal::OtherRegistration)
}

fn preflight(msi: &impl Inventory) -> Refusal {
    for product in PRODUCTS {
        if let Err(refusal) = check_product(msi, product) {
            return refusal;
        }
    }
    // The first installed or advertised relative suffices for a veto, regardless of architecture.
    match msi.family_registered(UPGRADE_CODE) {
        Ok(true) => Refusal::OtherRegistration,
        Ok(false) => Refusal::CutoverRequired,
        Err(code) => Refusal::InventoryError(code),
    }
}

#[cfg(windows)]
mod native {
    use super::{Inventory, Refusal, preflight};
    use std::io;

    #[link(name = "msi")]
    unsafe extern "system" {
        fn MsiGetProductInfoExW(
            code: *const u16,
            sid: *const u16,
            context: u32,
            property: *const u16,
            buffer: *mut u16,
            length: *mut u32,
        ) -> u32;
        fn MsiEnumRelatedProductsW(
            upgrade: *const u16,
            reserved: u32,
            index: u32,
            output: *mut u16,
        ) -> u32;
    }

    struct Installer;

    fn wide(value: &str) -> Vec<u16> {
        value.encode_utf16().chain(Some(0)).collect()
    }

    impl Inventory for Installer {
        fn property(&self, code: &str, name: &str) -> Result<String, u32> {
            let mut value = [0u16; 128]; // All three pinned installed properties fit; truncation is a refusal.
            let mut length = value.len() as u32;
            let result = unsafe {
                MsiGetProductInfoExW(
                    wide(code).as_ptr(),
                    std::ptr::null(),
                    4,
                    wide(name).as_ptr(),
                    value.as_mut_ptr(),
                    &mut length,
                )
            };
            if result != 0 {
                return Err(result);
            }
            if length as usize >= value.len() || value[length as usize] != 0 {
                return Err(13);
            }
            String::from_utf16(&value[..length as usize]).map_err(|_| 13)
        }

        fn family_registered(&self, upgrade: &str) -> Result<bool, u32> {
            let mut code = [0u16; 39];
            match unsafe {
                MsiEnumRelatedProductsW(wide(upgrade).as_ptr(), 0, 0, code.as_mut_ptr())
            } {
                0 => Ok(true),
                259 => Ok(false), // ERROR_NO_MORE_ITEMS at index zero
                error => Err(error),
            }
        }
    }

    pub(crate) fn probe() -> io::Result<()> {
        let (message, code) = match preflight(&Installer) {
            Refusal::Shipping(p) => (
                format!(
                    "VETO installed=3.0.4 context=machine state=5 architecture={} product={} package={}",
                    p.arch, p.code, p.package
                ),
                20,
            ),
            Refusal::OtherRegistration => ("VETO related-registration".to_string(), 21),
            Refusal::InventoryError(error) => (format!("UNRESOLVED msi-error={error}"), 22),
            Refusal::CutoverRequired => ("UNRESOLVED exclusive-cutover-required".to_string(), 23),
        };
        super::super::emit(&message)?;
        std::process::exit(code)
    }
}

#[cfg(windows)]
pub(super) use native::probe;

#[cfg(test)]
mod tests {
    use super::*;

    struct Msi<'a> {
        registered: Option<Product>,
        state: &'a str,
        package: &'a str,
        family: Result<bool, u32>,
    }
    impl Inventory for Msi<'_> {
        fn property(&self, code: &str, property: &str) -> Result<String, u32> {
            if self.registered.is_none_or(|p| p.code != code) {
                return Err(UNKNOWN_PRODUCT);
            }
            match property {
                "State" => Ok(self.state.into()),
                "VersionString" => Ok("3.0.4".into()),
                "PackageCode" => Ok(self.package.into()),
                _ => panic!("unrecognized property"),
            }
        }
        fn family_registered(&self, upgrade: &str) -> Result<bool, u32> {
            assert_eq!(upgrade, UPGRADE_CODE);
            self.family
        }
    }
    fn verify_veto(msi: &Msi, expected: Refusal) {
        assert_eq!(preflight(msi), expected);
    }
    #[test]
    fn either_original_machine_product_vetoes_and_changed_registration_is_distinct() {
        for p in PRODUCTS {
            let msi = Msi {
                registered: Some(p),
                state: "5",
                package: p.package,
                family: Ok(true),
            };
            verify_veto(&msi, Refusal::Shipping(p));
            verify_veto(&Msi { state: "1", ..msi }, Refusal::OtherRegistration);
            verify_veto(
                &Msi {
                    package: "different",
                    ..msi
                },
                Refusal::OtherRegistration,
            );
        }
    }
    #[test]
    fn an_unknown_family_member_and_query_failure_have_distinct_outcomes() {
        let msi = Msi {
            registered: None,
            state: "",
            package: "",
            family: Ok(true),
        };
        verify_veto(&msi, Refusal::OtherRegistration);
        verify_veto(
            &Msi {
                family: Err(5),
                ..msi
            },
            Refusal::InventoryError(5),
        );
    }
    #[test]
    fn empty_inventory_leaves_the_exclusive_cutover_unresolved() {
        let msi = Msi {
            registered: None,
            state: "",
            package: "",
            family: Ok(false),
        };
        assert_eq!(preflight(&msi), Refusal::CutoverRequired);
    }
}
