#![doc = include_str!("../README.md")]

use proc_macro::TokenStream;
use quote::quote;
use syn::{DeriveInput, LitStr, parse_macro_input};

/// Opt a CLI parser into the shared startup schema contract.
#[proc_macro_derive(Schema, attributes(schema))]
pub fn schema(item: TokenStream) -> TokenStream {
    let input = parse_macro_input!(item as DeriveInput);
    expand(&input)
        .unwrap_or_else(syn::Error::into_compile_error)
        .into()
}

fn expand(input: &DeriveInput) -> syn::Result<proc_macro2::TokenStream> {
    let mut name: Option<LitStr> = None;
    let mut about: Option<LitStr> = None;
    for attribute in &input.attrs {
        if attribute.path().is_ident("schema") {
            attribute.parse_nested_meta(|meta| {
                if meta.path.is_ident("name") && name.is_none() {
                    name = Some(meta.value()?.parse()?);
                } else if meta.path.is_ident("about") && about.is_none() {
                    about = Some(meta.value()?.parse()?);
                } else {
                    return Err(meta.error("expected unique name or about for an empty interface"));
                }
                Ok(())
            })?;
        }
    }
    let export = match (name, about) {
        (None, None) => quote!(::cli_schema::emit::<Self>()),
        (Some(name), Some(about)) => quote!(::cli_schema::emit_empty(#name, #about)),
        _ => {
            return Err(syn::Error::new_spanned(
                input,
                "an empty interface requires both name and about",
            ));
        }
    };
    let identifier = &input.ident;
    let (implementation, arguments, clause) = input.generics.split_for_impl();
    Ok(quote! {
        impl #implementation ::cli_schema::Schema for #identifier #arguments #clause {
            fn export_schema() -> ::core::option::Option<::std::process::ExitCode> {
                #export
            }
        }
    })
}
